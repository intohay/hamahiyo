import re
from pydub import AudioSegment
from generate import text_to_speech
import pdb
import io

def text_to_audio(text, output_file):
    # Split text into sentences based on punctuation and newlines
    sentences = re.split(r'(?<=[。！？])\s*|\n+', text)
    # 「濱岸」を「はまぎし」に変換
    sentences = [re.sub(r'濱岸', 'はまぎし', sentence) for sentence in sentences]
    
    # print(sentences)
    # Generate audio for each sentence and concatenate
    combined_audio = AudioSegment.empty()
    for sentence in sentences:
        print("Converting sentence: ", sentence)
        if sentence.strip():  # Skip empty sentences
            # Get binary wav data and convert to AudioSegment
            audio_data = text_to_speech(sentence)  # Assuming it returns wav binary data
            audio = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
            combined_audio += audio
    
    # Export the combined audio to a file
    combined_audio.export(output_file, format="mp3")

# Example usage
if __name__ == "__main__":
    # pdb.set_trace()
    with open("blog.txt" , "r") as f:
        text = f.read()

    
    text_to_audio(text, "output.mp3")
