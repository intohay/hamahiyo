import jaconv
import os
import yaml


base_dir = os.path.abspath(os.path.dirname(__file__))
bad_words_path = os.path.join(base_dir, '..', 'bad_words.yaml')


# YAMLファイルからbad_wordsを読み込む
def load_bad_words():
    with open(bad_words_path, "r", encoding="utf-8") as file:
        bad_words = yaml.safe_load(file)
    bad_words_list = []
    for genre in bad_words:
        bad_words_list.extend(bad_words[genre])
    return bad_words_list



def contains_bad_words(text):
    BAD_WORDS = load_bad_words()
    # テキストとbad wordsをひらがなに変換
    text_hiragana = jaconv.kata2hira(text.lower())
    for word in BAD_WORDS:
        word_hiragana = jaconv.kata2hira(word.lower().strip())
        if word_hiragana in text_hiragana:
            return True
    return False