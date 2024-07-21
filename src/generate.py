from transformers import AutoTokenizer,AutoModelForCausalLM


model_path = 'finetuned_gpt2'
model = AutoModelForCausalLM.from_pretrained(model_path)
tokenizer = AutoTokenizer.from_pretrained(model_path)

def getarate_messages(seed_sentence, num_sentences=1, num_messages=3):


    sentences = seed_sentence

    for _ in range(num_messages-1):
        x = tokenizer.encode(sentences, return_tensors="pt",

        add_special_tokens=False)  # 入力
        y = model.generate(x, #入力
                        min_length=20,  # 文章の最小長
                        max_length=100,  # 文章の最大長
                        do_sample=True,   # 次の単語を確率で選ぶ
                        top_k=100, # Top-Kサンプリング
                        top_p=0.95,  # Top-pサンプリング
                        temperature=1.2,  # 確率分布の調整
                        num_return_sequences=num_sentences,  # 生成する文章の数
                        pad_token_id=tokenizer.pad_token_id,  # パディングのトークンID
                        bos_token_id=tokenizer.bos_token_id,  # テキスト先頭のトークンID
                        eos_token_id=tokenizer.eos_token_id,  # テキスト終端のトークンID
                        )

        sentences = tokenizer.batch_decode(y, skip_special_tokens=False)[0]  # 特殊トークンをスキップして文章に変換
        
   
    result_sentences = []

   
    messages = sentences.split("</s>")
    for message in messages:
        if len(result_sentences) < num_messages and message.strip():
            result_sentences.append(message.strip())

    # special tokenを除く
    result_sentences = [sentence.replace(tokenizer.eos_token, '') for sentence in result_sentences]
    result_sentences = [sentence.replace(tokenizer.bos_token, '') for sentence in result_sentences]
    result_sentences = [sentence.replace(tokenizer.pad_token, '') for sentence in result_sentences]
    result_sentences = [sentence.replace(tokenizer.unk_token, '') for sentence in result_sentences]
    result_sentences = [sentence.replace(tokenizer.sep_token, '') for sentence in result_sentences]

   
    return result_sentences[:num_messages]


