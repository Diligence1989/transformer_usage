import os,sys
import json

titles = []
content = []
combines = []

with open('/home/songcaifu/kg/transformer_usage/text_summary/lcsts_tsv/valid.src.txt','r') as f:
    contents = f.readlines()
    contents = [i.replace('\n', '') for i in contents]
    print(contents[0:2])

with open('/home/songcaifu/kg/transformer_usage/text_summary/lcsts_tsv/valid.tgt.txt','r') as f:
    titles = f.readlines()
    titles = [i.replace('\n', '') for i in titles]
    print(titles[0:2])

for i, title in enumerate(titles):
    combines.append(title + '!=!' + contents[i])

#print(combines[-1])
with open() as f:
    f.writelines()
