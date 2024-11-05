import re
from pydub import AudioSegment
from generate import text_to_speech
import pdb
import io
from utilities import paraphrase_text
import time

def text_to_audio(text, output_file):
    # Split text into sentences based on punctuation and newlines
    sentences = re.split(r"\n+", text)

    sentences = [paraphrase_text(sentence) for sentence in sentences]



    # 空白行を削除
    sentences = [sentence for sentence in sentences if sentence.strip()]
    
    # Generate audio for each sentence and concatenate
    combined_audio = AudioSegment.empty()

    merged_sentences = []
    current_chunk = ""

    # 200文字以内になるように部分をマージ
    for sentence in sentences:
        # 次の文を追加して200文字以内なら追加する
        if len(current_chunk) + len(sentence) < 200:
            current_chunk += sentence + "\n"
        else:
            # 200文字を超える場合は今のチャンクを保存して、新しいチャンクを開始
            merged_sentences.append(current_chunk)
            current_chunk = sentence

    if current_chunk:
        merged_sentences.append(current_chunk)
    
    
    


    for sentence in merged_sentences:
        print("Converting sentence: ", sentence)
        if sentence.strip():  # Skip empty sentences
            retries = 3  # 再試行回数の設定
            audio_data = None

            # リトライのためのループ
            for attempt in range(retries):
                audio_data = text_to_speech(sentence)  # Assuming it returns wav binary data
                if audio_data is not None:
                    break  # 成功したらループを抜ける
                else:
                    print(f"Retrying conversion for sentence: {sentence} (attempt {attempt + 1})")
                    time.sleep(1)  # 少し待ってから再試行

            # audio_data が取得できたかどうかを確認
            if audio_data is not None:
                audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
                combined_audio += audio
            else:
                print(f"Failed to convert sentence after {retries} attempts: {sentence}")
    
    # Export the combined audio to a file
    combined_audio.export(output_file, format="mp3")

# Example usage
if __name__ == "__main__":
    # pdb.set_trace()
    with open("blog.txt" , "r") as f:
        text = f.read()

    
    text_to_audio(text, "output.mp3")
