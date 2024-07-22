# scheduler.py
import os
import threading
from flask import Flask
from generate import generate_messages
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# 上の階層にあるmessages.dbを参照するために相対パスを指定
base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, '..', 'instance/messages.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class MessageStock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String, nullable=False)

def contains_bad_words(text):
    BAD_WORDS = os.getenv('BAD_WORDS', '').split(',')
    for word in BAD_WORDS:
        if word.strip().lower() in text.lower():
            return True
    return False

def generate_and_store_messages():
    with app.app_context():
        # メッセージを生成してストックに追加
        messages = generate_messages("やほー！</s>", num_sentences=1, num_messages=2)
        for message in messages:
            if contains_bad_words(message):
                break
            
            new_message = MessageStock(message=message)
            db.session.add(new_message)
        else:
            db.session.commit()
            print("Messages generated and stored")

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=generate_and_store_messages, trigger="interval", minutes=1)
    scheduler.start()
    print("Scheduler started")
    threading.Event().wait()

if __name__ == '__main__':
    start_scheduler()
