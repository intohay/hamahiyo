from transformers import AutoTokenizer,AutoModelForCausalLM

import os


model_path = os.path.join(os.path.dirname(__file__), '../finetuned_gpt2')

model = AutoModelForCausalLM.from_pretrained(model_path)
tokenizer = AutoTokenizer.from_pretrained(model_path)

def generate_messages(seed_sentence, num_sentences=1, num_messages=3):


    messages = seed_sentence

    for _ in range(num_messages-1):
        x = tokenizer.encode(messages, return_tensors="pt",

        add_special_tokens=False)  # 入力
        y = model.generate(x, #入力
                        min_length=16,  # 文章の最小長
                        max_length=64,  # 文章の最大長
                        do_sample=True,   # 次の単語を確率で選ぶ
                        top_k=128, # Top-Kサンプリング
                        top_p=0.95,  # Top-pサンプリング
                        temperature=1.2,  # 確率分布の調整
                        num_return_sequences=num_sentences,  # 生成する文章の数
                        pad_token_id=tokenizer.pad_token_id,  # パディングのトークンID
                        bos_token_id=tokenizer.bos_token_id,  # テキスト先頭のトークンID
                        eos_token_id=tokenizer.eos_token_id,  # テキスト終端のトークンID
                        )

        messages = tokenizer.batch_decode(y, skip_special_tokens=False)[0]  # 特殊トークンをスキップして文章に変換
        
    
    messages = messages.split("</s>")
   

    


    # special tokenを除く
    messages = [message.replace(tokenizer.eos_token, '') for message in messages]
    messages = [message.replace(tokenizer.bos_token, '') for message in messages]
    messages = [message.replace(tokenizer.pad_token, '') for message in messages]
    messages = [message.replace(tokenizer.unk_token, '') for message in messages]
    messages = [message.replace(tokenizer.sep_token, '') for message in messages]

    
    # 空白は改行に
    messages = [message.replace(' ', '\n') for message in messages]
    
    # %%%や%%は「マンボウちゃん」に置換
    messages = [message.replace('%%%','マンボウちゃん') for message in messages]
    messages = [message.replace('%%','マンボウちゃん') for message in messages]

    # %は除外
    messages = [message.replace('%','') for message in messages]

    # ?は「？」に置換
    messages = [message.replace('?','？') for message in messages]
    # !は「！」に置換
    messages = [message.replace('!','！') for message in messages]

    # 空の要素は削除
    messages = [message for message in messages if message != '']
    # 前後の空白を削除
    messages = [message.strip() for message in messages]
    messages = messages[1:]
   
    return messages


if __name__ == '__main__':
    print(generate_messages("やほー！</s>", num_sentences=1, num_messages=2))