import jaconv
import os
import yaml
import requests
from bs4 import BeautifulSoup
import re

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


def extract_name_from_blog(url):
    # ブログをスクレイピング(テキストのみ)
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    # ブログの本文を取得
    article_div = soup.find("div", class_="c-blog-article__name")
    name = article_div.text
    

    return name.strip()

def scrape_blog(url):
    # ブログをスクレイピング(テキストのみ)
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    # ブログの本文を取得
    blog_text = ""
    article_div = soup.find("div", class_="c-blog-article__text")

    text_content = []
    for elem in article_div.descendants:
        if elem.name != "img" and isinstance(elem, str):  # Ignore <img> tags and capture text nodes
            text_content.append(elem.strip())


    # Join text content
    full_text = "\n".join(text_content)

    # httpで始まるURLを削除
    full_text = re.sub(r"http\S+", "", full_text)
    # @で始まる英数字を削除
    full_text = re.sub(r"@\w+", "", full_text)
    


    return full_text

if __name__ == "__main__":
    url = "https://www.hinatazaka46.com/s/official/diary/detail/57669?ima=0000&cd=member"
    print(scrape_blog(url))