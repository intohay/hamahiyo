import os
import random
import numpy as np
import tweepy
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
import time
import requests

# .envファイルから環境変数を読み込む
load_dotenv()

# Twitter APIのキーを設定
API_KEY = os.getenv('TWITTER_API_KEY')
API_KEY_SECRET = os.getenv('TWITTER_API_KEY_SECRET')
ACCESS_TOKEN = os.getenv('TWITTER_ACCESS_TOKEN')
ACCESS_TOKEN_SECRET = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')

# 認証を設定
client = tweepy.Client(
    consumer_key=API_KEY,
    consumer_secret=API_KEY_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET
)

# 確率分布データをロード
def load_distribution(file_path):
    df = pd.read_csv(file_path)
    # published_atをISO8601形式としてUTCのdatetime型に変換
    df['published_at'] = pd.to_datetime(df['published_at'], utc=True, errors='coerce')
    # 日本時間に変換
    df['published_at'] = df['published_at'] + pd.Timedelta(hours=9)
    # 各日の最初のメッセージ時刻を抽出
    df['date'] = df['published_at'].dt.date
    first_messages = df.groupby('date')['published_at'].min().dt.hour
    # 分布を計算
    distribution = first_messages.value_counts().sort_index()
    probabilities = distribution / distribution.sum()
    return probabilities

# 次の日のツイート時刻を決定
def decide_next_tweet_time(probabilities):
    # 時刻を確率分布からサンプリング
    sampled_hour = np.random.choice(probabilities.index, p=probabilities)
    # 分単位は一様分布からサンプリング
    sampled_minute = random.randint(0, 59)
    # 次の日のツイート時刻を計算
    now = datetime.now()
    next_day = now + timedelta(days=1)
    tweet_time = datetime(year=next_day.year, month=next_day.month, day=next_day.day,
                          hour=sampled_hour, minute=sampled_minute, second=0, microsecond=0)
    return tweet_time


def fetch_message():
    try:
        # GETリクエストを送信
        url = "https://mambouchan.com/hamahiyo/generate"
        response = requests.get(url)
        
        # レスポンスが正常か確認
        response.raise_for_status()  # ステータスコードが200以外の場合例外を発生

        # JSON形式でレスポンスを解析
        data = response.json()

        # `message` フィールドを抽出
        if "message" in data:
            message = data["message"]
            print(f"取得したメッセージ: {message}")
            return message
        else:
            print("レスポンスに `message` フィールドがありません。")
            return None

    except requests.exceptions.RequestException as e:
        print(f"HTTPリクエストエラー: {e}")
        return None
    except ValueError as e:
        print(f"JSON解析エラー: {e}")
        return None
    

def post_tweet(messages=None):

    if messages is not None:
        previous_tweet = None
        for message in messages:
            message = message + "\n#ハマヒヨトーク"
            if previous_tweet is None:
                # ツイートを投稿
                tweet = client.create_tweet(text=message)
                print(f"ツイートを投稿しました: {message}")
                previous_tweet = tweet.data['id']
            else:
                # 前のツイートにリプライとして投稿
                tweet = client.create_tweet(text=message, in_reply_to_tweet_id=previous_tweet)
                print(f"ツイートを続けました: {message}")
                previous_tweet = tweet.data['id']


        return


            


    try:
        # メッセージを取得
        message = fetch_message()
        if message is None:
            return

        # 一番最初の \t を \n に置き換える
        message = message.replace('\t', '\n', 1)
        
        # メッセージをタブ区切りで分割
        messages = message.split('\t')

        # 最初のツイートを投稿
        previous_tweet = None
        for part in messages:
            part = part + "\n#ハマヒヨトーク"
            if previous_tweet is None:
                # 最初のツイート
                tweet = client.create_tweet(text=part)
                previous_tweet = tweet.data['id']
                print(f"最初のツイートを投稿しました: {part}")
            else:
                # 前のツイートにリプライとして投稿
                tweet = client.create_tweet(text=part, in_reply_to_tweet_id=previous_tweet)
                previous_tweet = tweet.data['id']
                print(f"ツイートを続けました: {part}")

    except Exception as e:
        print(f"エラーが発生しました: {e}")


# メインスクリプト
def main():
    # 確率分布をロード
    probabilities = load_distribution('hiyoritalk.csv')
    

    # 最初のツイート時刻をハードコーディング
    first_tweet_time = datetime(year=2025, month=1, day=4, hour=14, minute=0, second=0)
    print(f"最初のツイート時刻: {first_tweet_time}")

    # 最初のツイートを待機して投稿
    sleep_duration = (first_tweet_time - datetime.now()).total_seconds()
    time.sleep(sleep_duration)
    post_tweet(messages=[
        "やほー！\n今日はねー早くに目が覚めたんだけど、ベットが冷たくて寝返りしよーって思ったらいつのまにか眠っちゃってました😂😂", 
        "でも寒かった🥲",
        "でも！！！\nお母さんがオール電化にしたから寒くないんだ🙄",
        "でもやっぱり寒いよ🥲",
        "マンボウちゃんは寒いの嫌い？"])


    while True:
        # 次の日のツイート時刻を決定
        tweet_time = decide_next_tweet_time(probabilities)
        print(f"次の日のツイート時刻: {tweet_time}")

        # ツイート時刻まで待機
        sleep_duration = (tweet_time - datetime.now()).total_seconds()
        time.sleep(sleep_duration)

        # ツイートを投稿
        post_tweet()

if __name__ == "__main__":
    main()
