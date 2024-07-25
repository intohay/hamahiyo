import os
import sys
import yaml
from flask import Flask
from generate import generate_messages
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from flask_migrate import Migrate
import fcntl
import jaconv

LOCK_FILE = 'accumulator.lock'

# ロックファイルを開く
fp = open(LOCK_FILE, 'w')

try:
    # ロックを取得
    fcntl.flock(fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
except IOError:
    print("Another instance is running, exiting.")
    sys.exit(1)

load_dotenv()
app = Flask(__name__)

# 上の階層にあるmessages.dbを参照するために相対パスを指定
base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, '..', 'instance/messages.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)

class MessageStock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String, nullable=False)
    is_released = db.Column(db.Boolean, default=False)

# YAMLファイルからbad_wordsを読み込む
def load_bad_words():
    with open("bad_words.yaml", "r", encoding="utf-8") as file:
        bad_words = yaml.safe_load(file)
    bad_words_list = []
    for genre in bad_words:
        bad_words_list.extend(bad_words[genre])
    return bad_words_list

BAD_WORDS = load_bad_words()


def contains_bad_words(text):
    # テキストとbad wordsをひらがなに変換
    text_hiragana = jaconv.kata2hira(text.lower())
    for word in BAD_WORDS:
        word_hiragana = jaconv.kata2hira(word.lower().strip())
        if word_hiragana in text_hiragana:
            return True
    return False


def generate_and_store_messages():
    with app.app_context():
        # メッセージを生成してストックに追加
        messages = generate_messages("やほー！</s>", num_sentences=100, num_messages=2)
        print(messages)
        for message in messages:
            for item in message:
                if contains_bad_words(item):
                    break
                
                

                new_message = MessageStock(message=item)
                db.session.add(new_message)
        else:
            db.session.commit()
            print("Messages generated and stored")

if __name__ == '__main__':
    generate_and_store_messages()

    # プロセス終了時にロックを解放
    fcntl.flock(fp, fcntl.LOCK_UN)
    fp.close()
