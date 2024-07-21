from flask import Flask, jsonify, request
from generate import getarate_messages
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "POST", "OPTIONS", "PUT", "DELETE"]}})


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