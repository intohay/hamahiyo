import os
import flask
from flask_migrate import Migrate
import yaml
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import jaconv
from accumulate import load_bad_words

load_dotenv()
app = Flask(__name__)

BAD_WORDS = load_bad_words()


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


@app.cli.command("delete_bad_words")
def delete_bad_words():
    messages_to_delete = MessageStock.query.all()
    bad_words_hiragana = [jaconv.kata2hira(word.lower().strip()) for word in BAD_WORDS]
    
    for message in messages_to_delete:
        message_text_hiragana = jaconv.kata2hira(message.message.lower())
        if any(word in message_text_hiragana for word in bad_words_hiragana):
            print(message)
            db.session.delete(message)

    db.session.commit()
    print(f"Deleted {len(messages_to_delete)} messages containing bad words.")