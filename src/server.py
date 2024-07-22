import os
from flask import Flask, jsonify, request
from generate import generate_messages
from flask_cors import CORS
from rq import Queue
from redis import Redis
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

# 上の階層の.envファイルを読み込む
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


app = Flask(__name__)
CORS(app)

base_dir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(base_dir, '..', 'messages.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

redis_conn = Redis()
q = Queue(connection=redis_conn)

BAD_WORDS = os.getenv('BAD_WORDS', '').split(',')

class MessageStock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String, nullable=False)




@app.route('/start-task', methods=['POST'])
def start_generating():
    job = q.enqueue(generate_messages, "やほー！</s>", num_sentences=1, num_messages=2)
    return jsonify({'job_id': job.get_id()}), 202

@app.route('/task-status/<job_id>', methods=['GET'])
def task_status(job_id):
    job = q.fetch_job(job_id)
    if job is None:
        return jsonify({'status': 'not found'}), 404


    if job.is_finished:
        messages = job.result
        # bad_wordsが含まれていたら再生成
        for message in messages:
            if contains_bad_words(message):
                job = q.enqueue(generate_messages, "やほー！</s>", num_sentences=1, num_messages=2)
                return jsonify({'status': 'retry', 'job_id': job.get_id()}), 202
            
        
        return jsonify({'status': job.get_status(), 'result': messages})
    elif job.is_failed:
        return jsonify({'status': job.get_status(), 'message': job.exc_info})
    else:
        return jsonify({'status': job.get_status()})
    
@app.route('/generate', methods=['GET'])
def get_message():
    message_stock = MessageStock.query.first()
    if message_stock:
        message = message_stock.message
        db.session.delete(message_stock)
        db.session.commit()
        return jsonify({'message': message})
    else:
       # ストックがない場合、新しいメッセージを生成するジョブをキューに追加
        job = q.enqueue(generate_messages, "やほー！</s>", num_sentences=1, num_messages=2)
        return jsonify({'job_id': job.get_id()}), 202

def contains_bad_words(text):
    for word in BAD_WORDS:
        if word in text.lower():
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

        
        
        


if __name__ == '__main__':
    env = os.getenv('FLASK_ENV', 'development')
    if env == 'production':
        debug_mode = False
    else:
        debug_mode = True

    # スケジューラを設定して定期的にメッセージを生成
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=generate_and_store_messages, trigger="interval", minutes=1)
    scheduler.start()

    try:
        # Flaskアプリケーションを実行
        app.run(debug=debug_mode)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown()