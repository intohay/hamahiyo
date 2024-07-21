from flask import Flask, jsonify, request
from generate import generate_messages
from flask_cors import CORS
from rq import Queue
from redis import Redis

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS", "PUT", "DELETE"]}})

redis_conn = Redis()
q = Queue(connection=redis_conn)


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
        # 空白は改行に
        messages = [message.replace(' ', '\n') for message in messages]

        # %%%や%%は「マンボウちゃん」に置換
        messages = [message.replace('%%%','マンボウちゃん') for message in messages]
        messages = [message.replace('%%','マンボウちゃん') for message in messages]

        # ?は「？」に置換
        messages = [message.replace('?','？') for message in messages]
        # !は「！」に置換
        messages = [message.replace('!','！') for message in messages]

        return jsonify({'status': job.get_status(), 'result': messages})
    elif job.is_failed:
        return jsonify({'status': job.get_status(), 'message': job.exc_info})
    else:
        return jsonify({'status': job.get_status()})
    


@app.route('/api/messages', methods=['GET', 'OPTIONS'])
def get_messages():
    if request.method == 'OPTIONS':
        return '', 204  # プレフライトリクエストには204 No Contentを返す
    

    messages = getarate_messages("やほー！</s>", num_sentences=1, num_messages=2)
    # 空白は改行に
    messages = [message.replace(' ', '\n') for message in messages]

    # %%%や%%は「マンボウちゃん」に置換
    messages = [message.replace('%%%','マンボウちゃん') for message in messages]
    messages = [message.replace('%%','マンボウちゃん') for message in messages]

    # ?は「？」に置換
    messages = [message.replace('?','？') for message in messages]
    # !は「！」に置換
    messages = [message.replace('!','！') for message in messages]


    return jsonify(messages[1:])

if __name__ == '__main__':
    app.run(debug=True)