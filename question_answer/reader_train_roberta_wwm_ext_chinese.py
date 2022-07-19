import torch
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForQuestionAnswering
from transformers import AdamW #, get_scheduler
from transformers.optimization import get_scheduler
import json
from tqdm.auto import tqdm
import collections
import random
import numpy as np
import os
import sys
sys.path.append('./')
from cmrc2018_evaluate import evaluate

#max_length = 384
max_length = 512
stride = 128
n_best = 20
max_answer_length = 30
batch_size = 4
learning_rate = 2e-5
epoch_num = 5

seed = 5
torch.manual_seed(seed)
torch.cuda.manual_seed(seed)
torch.cuda.manual_seed_all(seed)
random.seed(seed)
np.random.seed(seed)
os.environ['PYTHONHASHSEED'] = str(seed)

device = 'cuda' if torch.cuda.is_available() else 'cpu'
print(f'Using {device} device')

class CMRC2018(Dataset):
    def __init__(self, data_file):
        self.data = self.load_data(data_file)
    
    def load_data(self, data_file):
        Data = {}
        with open(data_file, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
            idx = 0
            for article in json_data['data']:
                title = article['title']
                context = article['paragraphs'][0]['context']
                for question in article['paragraphs'][0]['qas']:
                    q_id = question['id']
                    ques = question['question']
                    text = [ans['text'] for ans in question['answers']]
                    answer_start = [ans['answer_start'] for ans in question['answers']]
                    Data[idx] = {
                        'id': q_id,
                        'title': title,
                        'context': context, 
                        'question': ques,
                        'answers': {
                            'text': text,
                            'answer_start': answer_start
                        }
                    }
                    idx += 1
        return Data
    
    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        return self.data[idx]

train_data = CMRC2018('cmrc2018/cmrc2018_train.json')
valid_data = CMRC2018('cmrc2018/cmrc2018_dev.json')
test_data = CMRC2018('cmrc2018/cmrc2018_trial.json')

#model_checkpoint = 'bert-base-chinese'
model_checkpoint = "hfl/chinese-roberta-wwm-ext-large"
tokenizer = AutoTokenizer.from_pretrained(model_checkpoint)
model = AutoModelForQuestionAnswering.from_pretrained(model_checkpoint)
model = model.to(device)

def train_collote_fn(batch_samples):
    batch_question, batch_context, batch_answers = [], [], []
    for sample in batch_samples:
        batch_question.append(sample['question'])
        batch_context.append(sample['context'])
        batch_answers.append(sample['answers'])
    batch_data = tokenizer(
        batch_question,
        batch_context,
        max_length=max_length,
        truncation="only_second",
        stride=stride,
        return_overflowing_tokens=True,
        return_offsets_mapping=True,
        padding='max_length'
    )
    
    offset_mapping = batch_data.pop('offset_mapping')
    sample_map = batch_data.pop('overflow_to_sample_mapping')

    start_positions = []
    end_positions = []
    
    for i, offset in enumerate(offset_mapping):
        sample_idx = sample_map[i]
        answer = batch_answers[sample_idx]
        start_char = answer['answer_start'][0]
        end_char = answer['answer_start'][0] + len(answer['text'][0])
        sequence_ids = batch_data.sequence_ids(i)

        # Find the start and end of the context
        idx = 0
        while sequence_ids[idx] != 1:
            idx += 1
        context_start = idx
        while sequence_ids[idx] == 1:
            idx += 1
        context_end = idx - 1

        # If the answer is not fully inside the context, label is (0, 0)
        if offset[context_start][0] > start_char or offset[context_end][1] < end_char:
            start_positions.append(0)
            end_positions.append(0)
        else:
            # Otherwise it's the start and end token positions
            idx = context_start
            while idx <= context_end and offset[idx][0] <= start_char:
                idx += 1
            start_positions.append(idx - 1)

            idx = context_end
            while idx >= context_start and offset[idx][1] >= end_char:
                idx -= 1
            end_positions.append(idx + 1)
    batch_data['start_positions'] = start_positions
    batch_data['end_positions'] = end_positions
    return batch_data

def test_collote_fn(batch_samples):
    batch_id, batch_question, batch_context = [], [], []
    for sample in batch_samples:
        batch_id.append(sample['id'])
        batch_question.append(sample['question'])
        batch_context.append(sample['context'])
    batch_data = tokenizer(
        batch_question,
        batch_context,
        max_length=max_length,
        truncation="only_second",
        stride=stride,
        return_overflowing_tokens=True,
        return_offsets_mapping=True,
        padding="max_length",
    )
    
    sample_map = batch_data.pop('overflow_to_sample_mapping')
    example_ids = []

    for i in range(len(batch_data['input_ids'])):
        sample_idx = sample_map[i]
        example_ids.append(batch_id[sample_idx])

        sequence_ids = batch_data.sequence_ids(i)
        offset = batch_data["offset_mapping"][i]
        batch_data["offset_mapping"][i] = [
            o if sequence_ids[k] == 1 else None for k, o in enumerate(offset)
        ]
    batch_data["example_id"] = example_ids
    return batch_data

train_dataloader = DataLoader(train_data, batch_size=batch_size, shuffle=True, collate_fn=train_collote_fn)
valid_dataloader = DataLoader(valid_data, batch_size=batch_size, shuffle=False, collate_fn=test_collote_fn)

print('train set size: ', )
print(len(train_data), '->', sum([len(batch_data['input_ids']) for batch_data in train_dataloader]))
print('valid set size: ')
print(len(valid_data), '->', sum([len(batch_data['input_ids']) for batch_data in valid_dataloader]))

def train_loop(dataloader, model, optimizer, lr_scheduler, epoch, total_loss):
    progress_bar = tqdm(range(len(dataloader)))
    progress_bar.set_description(f'loss: {0:>7f}')
    finish_batch_num = (epoch-1) * len(dataloader)
    
    model.train()
    for batch, batch_data in enumerate(dataloader, start=1):
        batch_data = {k: torch.tensor(v).to(device) for k, v in batch_data.items()}
        outputs = model(**batch_data)
        loss = outputs.loss

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        lr_scheduler.step()

        total_loss += loss.item()
        progress_bar.set_description(f'loss: {total_loss/(finish_batch_num + batch):>7f}')
        progress_bar.update(1)
    return total_loss

def test_loop(dataloader, dataset, model, mode='Test'):
    assert mode in ['Valid', 'Test']

    all_example_ids = []
    all_offset_mapping = []
    for batch_data in dataloader:
        all_example_ids += batch_data['example_id']
        all_offset_mapping += batch_data['offset_mapping']

    model.eval()
    start_logits = []
    end_logits = []
    for batch_data in tqdm(dataloader):
        del batch_data['offset_mapping']
        del batch_data['example_id']
        batch_data = {k: torch.tensor(batch_data[k]).to(device) for k in batch_data.keys()}
        with torch.no_grad():
            outputs = model(**batch_data)
        start_logits.append(outputs.start_logits.cpu().numpy())
        end_logits.append(outputs.end_logits.cpu().numpy())
    start_logits = np.concatenate(start_logits)
    end_logits = np.concatenate(end_logits)
    
    example_to_features = collections.defaultdict(list)
    for idx, feature_id in enumerate(all_example_ids):
        example_to_features[feature_id].append(idx)
    
    theoretical_answers = [
        {"id": dataset[idx]["id"], "answers": dataset[idx]["answers"]} for idx in range(len(dataset))
    ]
    predicted_answers = []
    for idx in tqdm(range(len(dataset))):
        example_id = dataset[idx]["id"]
        context = dataset[idx]["context"]
        answers = []

        # Loop through all features associated with that example
        for feature_index in example_to_features[example_id]:
            start_logit = start_logits[feature_index]
            end_logit = end_logits[feature_index]
            offsets = all_offset_mapping[feature_index]

            start_indexes = np.argsort(start_logit)[-1 : -n_best - 1 : -1].tolist()
            end_indexes = np.argsort(end_logit)[-1 : -n_best - 1 : -1].tolist()
            for start_index in start_indexes:
                for end_index in end_indexes:
                    if offsets[start_index] is None or offsets[end_index] is None:
                        continue
                    if (end_index < start_index or end_index-start_index+1 > max_answer_length):
                        continue
                    answers.append({
                        "start": offsets[start_index][0], 
                        "text": context[offsets[start_index][0] : offsets[end_index][1]], 
                        "logit_score": start_logit[start_index] + end_logit[end_index],
                    })
        # Select the answer with the best score
        if len(answers) > 0:
            best_answer = max(answers, key=lambda x: x["logit_score"])
            predicted_answers.append({
                "id": example_id, 
                "prediction_text": best_answer["text"], 
                "answer_start": best_answer["start"]
            })
        else:
            predicted_answers.append({
                "id": example_id, 
                "prediction_text": "", 
                "answer_start": 0
            })
    result = evaluate(predicted_answers, theoretical_answers)
    print(f"{mode} F1: {result['f1']:>0.2f} EM: {result['em']:>0.2f} AVG: {result['avg']:>0.2f}\n")
    return result

optimizer = AdamW(model.parameters(), lr=learning_rate)
lr_scheduler = get_scheduler(
    "linear",
    optimizer=optimizer,
    num_warmup_steps=0,
    num_training_steps=epoch_num*len(train_dataloader),
)

# 测试下未经finetune的roberta版本效果
#valid_scores = test_loop(valid_dataloader, valid_data, model, mode='Valid')

total_loss = 0.
best_avg_score = 0.
for t in range(epoch_num):
    print(f"Epoch {t+1}/{epoch_num}\n-------------------------------")
    total_loss = train_loop(train_dataloader, model, optimizer, lr_scheduler, t+1, total_loss)
    valid_scores = test_loop(valid_dataloader, valid_data, model, mode='Valid')
    avg_score = valid_scores['avg']
    if avg_score > best_avg_score:
        best_avg_score = avg_score
        print('saving new weights...\n')
        torch.save(model.state_dict(), f'epoch_{t+1}_valid_avg_{avg_score:0.4f}_model_weights.bin')
print("Done!")
