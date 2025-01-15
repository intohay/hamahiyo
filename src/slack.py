import os
import re
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from generate import retry_completion, tokenize

load_dotenv()

# 環境変数からトークンを取得
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")  # Bot User OAuth Token
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")  # App-Level Token

# Slackアプリの初期化
app = App(token=SLACK_BOT_TOKEN)

# メンションされたときのイベントをハンドル
@app.event("app_mention")
def mention_handler(event, say, client):
    user = event["user"]  # メンションしたユーザーID
    text = event["text"]  # メッセージ内容
    channel = event["channel"]  # メッセージが送信されたチャンネル
    
    text = re.sub(r"<@[A-Z0-9]+>", "", text)  # メンションを削除

    print(f"text: {text}")

    if text.startswith("\n"):
        prompt = f"Q: {text.strip()}\nA: "
    else:
        
        def get_token_count(text):
            return len(tokenize(text))
        

        response = client.conversations_history(channel=channel, limit=10)
        messages = response["messages"]

        chat_history = ""
       
        for message in messages:
            if "user" in message and "text" in message:
                
                
                
                if message["user"] == user and f"<@{app.client.auth_test()['user_id']}>" in message["text"]:
                    history_text = re.sub(r"<@[A-Z0-9]+>", "", message["text"]).strip()
                    new_chat_history = f"Q: {history_text}\n" + chat_history
                elif message["user"] == app.client.auth_test()['user_id'] and f"<@{user}>" in message["text"]:
                    history_text = re.sub(r"<@[A-Z0-9]+>", "", message["text"]).strip()
                    new_chat_history = f"A: {history_text}\n" + chat_history

                if get_token_count(new_chat_history) > 200:
                    break
                
                chat_history = new_chat_history

                # \nをnew chatの合図とする
                if message["user"] == user and re.match(r"^<@[A-Z0-9]+>\n", message["text"]):
                    break

        
        prompt = f"{chat_history}A: "
            

        

    try:
        
        print(f"prompt: \n{prompt}")
        answer = retry_completion(prompt, 1, 1.2, 3, ["\t", "\n", "Q:"])

        print(f"Answer: {answer}")
        response_message = f"<@{user}>\n{answer}"
        say(response_message, channel=channel)

    except Exception as e:
        print(f"An error occurred: {str(e)}")
        say("もう一回言ってみて！", channel=channel)





# Socket Modeでアプリを起動
if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
