import jaconv
import os
import yaml
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
base_dir = os.path.abspath(os.path.dirname(__file__))
bad_words_path = os.path.join(base_dir, '..', 'bad_words.yaml')



text = r'[0-9A-Za-zぁ-ヶ一-龠]'
non_text = r'[^\n!?！？0-9A-Za-zぁ-ヶ一-龠]'
allow_text = r'[ovっつ゜ニノ三二ﾛ]'
hw_kana = r'[ｦ-ﾟ]'
open_bracket = r'[\(∩꒰（]'
close_bracket = r'[\)∩꒱）]'
around_face = r'(?:' + non_text + r'|' + allow_text + r')*'
face = r'(?!(?:' + text + r'|' + hw_kana + r'){3,}).{3,}'
face_char_pattern = around_face + open_bracket + face + close_bracket + around_face

face_char_regex = re.compile(face_char_pattern)

# テスト文字列に適用する関数
def remove_faces(text):
    return face_char_regex.sub('', text)


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


def scrape_body(soup):
    body_element = str(soup.find("div",
                                class_='c-blog-article__text'))

    body_element = re.sub('<br.*?>', '\n', body_element)  # <br>タグを改行に変換
    body_element = re.sub('</div>', '', body_element)  # <div>を消去
    body_element = re.sub('<div>', '\n', body_element)  # </div>タグを改行に変換

    body_content = re.sub('<.+?>', '', body_element)  # 他のタグを消去
    
    return body_content


def scrape_blog(url):
    # ブログをスクレイピング(テキストのみ)
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    full_text = scrape_body(soup)
        
    
   
    # httpで始まるURLを削除
    full_text = re.sub(r"http\S+", "", full_text)
    # @で始まる英数字を削除
    full_text = re.sub(r"@\w+", "", full_text)

    # \nで分割
    full_text = full_text.split("\n")

    # 空白行を削除
    full_text = [line for line in full_text if line.strip()]

    # 先頭と末尾の空白を削除
    full_text = [line.strip() for line in full_text]

    # リストを文字列に変換
    full_text = "\n".join(full_text)
    full_text = remove_faces(full_text)
    print(full_text)
    return full_text

def extract_date_from_blog(url):
    # ブログをスクレイピング(テキストのみ)
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")

    # ブログの本文を取得
    article_div = soup.find("div", class_="c-blog-article__date")
    date_str = article_div.text.strip()
    # 2024.10.28 14:49という形式になっているので、datetimeに変換し、2024-10-28という形式に変換
    date_str = datetime.strptime(date_str, "%Y.%m.%d %H:%M").strftime("%Y-%m-%d")

    return date_str

    

def paraphrase_text(text):
    
    eng_jpn_dict = {
        "濱岸": "はまぎし",
        "日向坂46": "ひなたざかフォーティーシックス",
        "ひなた坂46": "ひなたざかフォーティーシックス",
        "SHOWROOM": "ショールーム",
        "12th": "12枚目",
        "OSAKA GIGANTIC MUSIC FESTIVAL 2024": "大阪ジャイガンティックミュージックフェスティバル2024",
        "46時間TV": "46時間テレビ",
        "CHAGU CHAGU ROCK FESTIVAL 2024" : "チャグチャグロックフェスティバル2024",
        "LIVE": "ライブ",
        "11th": "11枚目",
        "10th": "10枚目",
        "9th": "9枚目",
        "8th": "8枚目",
        "7th": "7枚目",
        "6th": "6枚目",
        "5th": "5枚目",
        "4th": "4枚目",
        "3rd": "サード",
        "2nd": "セカンド",
        "1st": "ファースト",
        "MV": "エムブイ",
        "WE R!": "ウィーアー",
        "Single" : "シングル",
        "Let's  Be Happy": "レッツビーハッピー",
        "HappyTrainTour2023": "ハッピートレインツアー2023",
        "andGIRL": "アンドガール",
        "W-KEYAKI FES": "ダブルけやきフェス",
        "HappyTrain": "ハッピートレイン",
        "Am I ready？": "アムアイレディ",
        "CDTVライブ！ライブ！30周年SP": "カウントダウンティービーライブライブ30周年スペシャル",
        "CDTV": "カウントダウンティービー",
        "HappySmileTour 2022": "ハッピースマイルツアー2022",
        "Instagram": "インスタグラム",
        "hiyotan928_official": "ひよたん928 アンダーバー オフィシャル",
        "Midnight": "ミッドナイト",
        "TGC": "ティージーシー",
        "with": "ウィズ",
        "Twitter": "ツイッター",
        "ODDTAXI": "オッドタクシー",
        "SPRING/SUMMER": "スプリング/サマー",
        "KOEHARU LIVESHOW": "コエハル ライブショー",
        "ZIP": "ジップ",
        "BANANAFISH": "バナナフィッシュ",
        "Re:ゼロから始まる異世界生活": "リ ゼロから始まる異世界生活",
        "bis": "ビス",
        "blt graph.": "ビーエルティーグラフ",
        "BLT": "ビーエルティ",
        "YouTuber": "ユーチューバー",
        "YouTube": "ユーチューブ",
        "ASMR": "エーエスエムアール",
        "DRAWING SMASH": "ドローイングスマッシュ",
        "anan": "アンアン",
        "UV": "ユーブイ",
        "NARUTO": "ナルト",
        "DASADA": "ダサダ",
        "Fall&Winter Collection": "フォールアンドウィンターコレクション",
        "fall&winter collection": "フォールアンドウィンターコレクション",
        "Lypo-C": 'リポシー',
        "WebCM": "ウェブシーエム",
        "１ｓｔ": "ファースト",
        "HINATAZAKA46 Live Online，YES！with YOU！": "日向坂46 ライブ オンライン イエス ウィズ ユー",
        "BBQ": "バーベキュー",
        "Innisfree": "イニスフリー",
        "MAKEUP FOREVER": "メイクアップフォーエバー",
        "HDパウダー": "エイチディーパウダー",
        "Luscious Lips": "ラシャスリップス",
        "PAY・DAY": "ペイデイ",
        "FASHION_SHOW": "ファッションショー",
        "UNO": "ウノ",
        "ねむ岸": "ねむぎし",
        "LINE" : "ライン",
        "ALLLIVENIPPON": "オールライブニッポン",
        "DVD": "ディーブイディー",
        "3days" : "スリーデイズ",
        "3Days" : "スリーデイズ",
        "Mnet Asian Music Awards": "エムネットエイジアンミュージックアワード",
        "KEYABINGO！4": "ケヤビンゴ フォー",
        "KEYABINGO4": "ケヤビンゴ フォー",
        "CoCo壱": "ココイチ",
        "de HAPPY!": "デ ハッピー",
        "Hot Stuff": "ホットスタッフ",
        "乃木坂46": "のぎざかフォーティーシックス",
        "けやき坂46": "ひらがなけやきざかフォーティーシックス",
        "櫻坂46": "さくらざかフォーティーシックス",
        "欅坂46": "けやきざかフォーティーシックス",
        "U18": "アンダーエイティーン",
        "Flash": "フラッシュ",
        "FLASH": "フラッシュ",
        "Happy Birthday": "ハッピーバースデー",
        "JK": "ジェーケー",
        "MAX": "マックス",
        "kg": "キログラム",
        "graduation": "グラデュエーション",
        "SHIBUYA TSUTAYA": "シブヤ ツタヤ",
        "MARQUEE": "マーキー",
        "MC": "エムシー",
        "Happy Magical Tour": "ハッピーマジカルツアー",
        }
    
    for key, value in eng_jpn_dict.items():
        text = text.replace(key, value)

    
    return text


if __name__ == "__main__":
    url = "https://www.hinatazaka46.com/s/official/diary/detail/40153?ima=0000&cd=member"
    scrape_blog(url)