import os
import sys
from flask import Flask
from generate import completion
from flask_sqlalchemy import SQLAlchemy
# from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from flask_migrate import Migrate
import fcntl
from utilities import contains_bad_words
from transformers import AutoTokenizer
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

tokenizer = AutoTokenizer.from_pretrained("tokyotech-llm/Llama-3.1-Swallow-8B-Instruct-v0.3")


def generate_and_store_messages():

    system_prompt = [{"role": "system", "content": "あなたは「ハマヒヨちゃん」というキャラクターです。一人称は「私」または「ヒヨタン」を使い、それ以外使わないで下さい。"}]

    with app.app_context():
        # メッセージを生成してストックに追加
        # messages_list = generate_messages("<s>やほー！[SEP]", num_sentences=50)


        for i in range(150):

            
            prompt = tokenizer.apply_chat_template(system_prompt, add_generation_prompt=True, tokenize=True) + tokenizer.encode("やほー！\t", add_special_tokens=False)


            messages = "やほー！\t" + completion(prompt)
            
            
            if contains_bad_words(messages):
                continue
            
            new_message = MessageStock(message=messages)
            db.session.add(new_message)
            db.session.commit()
            # print(new_message.message)
        
           
        print("Messages generated and stored")

if __name__ == '__main__':
    generate_and_store_messages()

    # プロセス終了時にロックを解放
    fcntl.flock(fp, fcntl.LOCK_UN)
    fp.close()
