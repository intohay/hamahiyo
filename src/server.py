import os
from flask import Flask, jsonify, request
from generate import generate_messages
from flask_cors import CORS
from rq import Queue
from redis import Redis
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from flask_migrate import Migrate  
import jaconv
from accumulate import load_bad_words

# 上の階層の.envファイルを読み込む
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


app = Flask(__name__)
CORS(app)

base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, '..', 'instance/messages.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)  

redis_conn = Redis()
q = Queue(connection=redis_conn)

BAD_WORDS = os.getenv('BAD_WORDS', '').split(',')

class MessageStock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String, nullable=False)
    is_released = db.Column(db.Boolean, default=False)



    
@app.route('/generate', methods=['GET'])
def get_message():
    message_stock = MessageStock.query.filter_by(is_released=False).order_by(MessageStock.id.desc()).first()
    if message_stock:
        message = message_stock.message
        message_stock.is_released = True
        db.session.commit()
        return jsonify({'message': message})
    else:
       # ストックがない場合、新しいメッセージを生成するジョブをキューに追加
        message = "ストック切れだよー！しばしお待ちを！"
        # job = q.enqueue(generate_messages, "やほー！</s>", num_sentences=1, num_messages=2)
        return jsonify({'message': message})


@app.cli.command("delete_bad_words")
def delete_bad_words():
    BAD_WORDS = load_bad_words()
    messages_to_delete = MessageStock.query.all()
    bad_words_hiragana = [jaconv.kata2hira(word.lower().strip()) for word in BAD_WORDS]
    
    for message in messages_to_delete:
        message_text_hiragana = jaconv.kata2hira(message.message.lower())
        if any(word in message_text_hiragana for word in bad_words_hiragana):
            print(message.message)
            db.session.delete(message)

    db.session.commit()

    print(f"Deleted {len(messages_to_delete)} messages containing bad words.")


        
        
if __name__ == '__main__':
    env = os.getenv('FLASK_ENV', 'development')
    if env == 'production':
        debug_mode = False
    else:
        debug_mode = True


    app.run(debug=debug_mode)
   