import os
import sys
import json


def preprocess(src, tgt, savefile):
    titles = []
    content = []
    combines = []
    # with open('/home/songcaifu/kg/transformer_usage/text_summary/lcsts_tsv/valid.src.txt','r') as f:
    with open(src, 'r') as f:
        contents = f.readlines()
        contents = [i.replace('\n', '') for i in contents]

    # with open('/home/songcaifu/kg/transformer_usage/text_summary/lcsts_tsv/valid.tgt.txt','r') as f:
    with open(tgt, 'r') as f:
        titles = f.readlines()
        titles = [i.replace('\n', '') for i in titles]

    for i, title in enumerate(titles):
        combines.append(title + '!=!' + contents[i]+'\n')

    with open(savefile, 'w') as f:
        f.writelines(combines)


#preprocess('lcsts_tsv/train.src.txt', 'lcsts_tsv/train.tgt.txt', 'lcsts_tsv/data1.tsv')
#preprocess('lcsts_tsv/valid.src.txt', 'lcsts_tsv/valid.tgt.txt', 'lcsts_tsv/data2.tsv')
#preprocess('lcsts_tsv/test.src.txt', 'lcsts_tsv/test.tgt.txt', 'lcsts_tsv/data3.tsv')
