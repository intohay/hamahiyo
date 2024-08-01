from transformers import AutoTokenizer,AutoModelForCausalLM

import os
import re


model_path = os.path.join(os.path.dirname(__file__), '../finetuned_gpt2')

model = AutoModelForCausalLM.from_pretrained(model_path)
tokenizer = AutoTokenizer.from_pretrained(model_path)

def generate_messages(seed_sentence, min_length=16, max_length=128, num_sentences=1):

    x = tokenizer.encode(seed_sentence, return_tensors="pt", add_special_tokens=False)  # 入力

    y = model.generate(x, #入力
                    min_length=min_length,  # 文章の最小長
                    max_length=max_length,  # 文章の最大長
                    do_sample=True,   # 次の単語を確率で選ぶ
                    top_k=50, # Top-Kサンプリング
                    top_p=0.95,  # Top-pサンプリング
                    temperature=1.2,  # 確率分布の調整
                    num_return_sequences=num_sentences,  # 生成する文章の数
                    pad_token_id=tokenizer.pad_token_id,  # パディングのトークンID
                    bos_token_id=tokenizer.bos_token_id,  # テキスト先頭のトークンID
                    eos_token_id=tokenizer.eos_token_id,  # テキスト終端のトークンID
                    )

    messages = tokenizer.batch_decode(y, skip_special_tokens=False)  # 特殊トークンをスキップして文章に変換




    # special tokenを除く

    messages = [message.replace(tokenizer.bos_token, '') for message in messages]
    messages = [message.replace(tokenizer.pad_token, '') for message in messages]
    messages = [message.replace(tokenizer.unk_token, '') for message in messages]
    messages = [message.replace(tokenizer.eos_token, '') for message in messages]



    # ?は「？」に置換
    messages = [message.replace('?','？') for message in messages]
    # !は「！」に置換
    messages = [message.replace('!','！') for message in messages]

    # [NEWLINE]は改行に
    messages = [message.replace('[NEWLINE]', '\n') for message in messages]

    messages = [message.replace('<emoji>', '') for message in messages]
    messages = [message.replace('</emoji>', '') for message in messages]

    messages = [re.sub(r"(\[SEP\]){2,}", "[SEP]", message) for message in messages]

    message_lists = [message.split("[SEP]") for message in messages]
    
    message_lists = [[message.strip() for message in message_list] for message_list in  message_lists]
    
    messages = ["[SEP]".join(message_list) for message_list in message_lists]

    return messages


if __name__ == '__main__':
    print(generate_messages("<s>やほー！[SEP]", num_sentences=2))
