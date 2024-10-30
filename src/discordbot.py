import os
import discord
import asyncio
from discord.ext import commands, tasks
from dotenv import load_dotenv
import requests
from datetime import datetime, time, timedelta
import pdb
import re
from discord import File
from generate import n_messages_completion, tokenize, text_to_speech
import aiohttp
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents)

import unicodedata

def normalize_text(text):
    # 全角と半角を統一
    return unicodedata.normalize('NFKC', text)


# def generate_message_from_prompt(prompt):
#     original_prompt = prompt
#     # 全角の空白は半角に変換
#     prompt = prompt.replace('　', ' ')

#     # prompt = prompt.replace('\n\n', '[SEP]')  # \n\nは[SEP]に変換
#     # \nは[NEWLINE]に変換
#     prompt = prompt.replace('\n', '[NEWLINE]')
    

#     # gpt-2 を使う generate_messages をインポート
#     from generate import generate_messages
    
#     # メッセージを生成
#     messages = generate_messages(prompt, max_length=64, num_sentences=1)
#     message = messages[0]
#     message_list = message.split('[SEP]')[:2]  # [SEP] 以降の文章を削除
#     message = '\n'.join(message_list)
    
#     print(f'Prompt: {original_prompt}')
#     print(f'Message: {message}')
#     i = 0
#     j = 0
   
#     while i < len(original_prompt):
#         p = original_prompt[i]
#         m = message[j]
#         if normalize_text(p.strip()) == normalize_text(m.strip()):
#             i += 1
#             j += 1
#         else:
#             message = message[:j] + message[j+1:]
    
#     prompt = normalize_text(prompt)
#     message = normalize_text(message)
#     message = re.sub(re.escape(prompt), f'**{prompt}**', message, count=1, flags=re.UNICODE)

#     # !は「！」に置換
#     message = message.replace('!', '！')
#     # ?は「？」に置換
#     message = message.replace('?', '？')
#     return message

# -tオプションを抽出するための関数
def extract_t_option(prompt: str, default_value: float = 1.2):
    """
    プロンプトから -t <value> オプションを抽出し、オプションの数値とクリーンなプロンプトを返す。

    Parameters:
    - prompt (str): ユーザーからの入力文字列
    - default_value (float): tオプションが無かった場合のデフォルト値

    Returns:
    - t_value (float): tオプションの値（デフォルト値の場合もある）
    - clean_prompt (str): tオプションを取り除いた後のプロンプト
    """
    # 正規表現パターンで -t <float> を探す（整数も小数点もサポート）
    t_option_pattern = r'-t\s+([0-9]*\.?[0-9]+)'
    t_option_match = re.search(t_option_pattern, prompt)

    if t_option_match:
        t_value = float(t_option_match.group(1))  # -t の数値を float で抽出
        clean_prompt = re.sub(t_option_pattern, '', prompt).strip()  # -tオプション部分を削除
    else:
        t_value = default_value  # デフォルト値を使用
        clean_prompt = prompt.strip()  # オプションが無い場合もクリーンアップ

    return t_value, clean_prompt

# -dオプションを抽出するための関数(デバッグ用)
def extract_d_option(prompt: str):
    d_option_pattern = r'-d'
    d_option_match = re.search(d_option_pattern, prompt)

    if d_option_match:
        # -dオプションを取り除く
        clean_prompt = re.sub(d_option_pattern, '', prompt).strip()

        return True, clean_prompt
    
    return False, prompt


def retry_completion(prompt, num=1, temperature=1.2, max_retries=3, stop=["\t", "\n", "Q:"]):
    try_count = 0
    answer = None

    while try_count < max_retries:
        try:
            # 回答生成
            answer = n_messages_completion(prompt, num=num, temperature=temperature, stop=stop)
            if answer and answer != "":
                break  # 成功したらループを抜ける
            else:
                answer = "もう一回言ってみて！"
        except Exception as e:
            answer = f"An error occurred: {str(e)}"
            break  # デバッグモードなら即座に終了
        try_count += 1

    return answer

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await bot.tree.sync(guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
    print(f"{bot.user.name} is connected to the following guilds:")
    for guild in bot.guilds:
        print(f"{guild.name} (id: {guild.id})")
    
    schedule_daily_yaho()

@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    is_mention = bot.user.mentioned_in(message)
    is_reply = message.reference is not None and message.reference.resolved.author == bot.user

    # トークン数カウント用の関数
    def get_token_count(text):
        return len(tokenize(text))
    
    # Botがメンションされたかどうか確認
    if is_mention or is_reply:

        # メンションされたら応答
        question = message.content.replace(f'<@{bot.user.id}>', '').strip()

        is_debug, question = extract_d_option(question)  # -dオプションを抽出
        temperature, question = extract_t_option(question)  # -tオプションを抽出


        if is_reply:

            current_message = message
            # system_prompt = "質問返しまーす！\t"
            prompt = f"Q: {question}\nA:"
            while current_message.reference is not None:
                
                previous_message = await current_message.channel.fetch_message(current_message.reference.message_id)
                previous_answer = previous_message.content

                if previous_message.reference:
                    more_previous_message = await current_message.channel.fetch_message(previous_message.reference.message_id)
                    previous_question = more_previous_message.content.replace(f'<@{bot.user.id}>', '').strip()
                else:
                    break

                new_prompt = f"Q: {previous_question}\nA: {previous_answer}\n" + prompt
                if get_token_count(new_prompt) > 200:
                    break
                prompt = new_prompt

                current_message = more_previous_message
            
            
            

        else:
            prompt = f"Q: {question}\nA:"

        print(prompt)
        answer = retry_completion(prompt, num=1, temperature=temperature, max_retries=3, stop=["\t", "Q:"])


        # メッセージにリプライ
        await message.reply(answer)

@bot.tree.command(name='yaho', description='やほー！から始まる文章を返します', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def yaho(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get('https://mambouchan.com/hamahiyo/generate') as response:
            data = await response.json()
            message = data['message']
            message_list = re.split(r'[\t\n]', message)[:3]
            message = '\n'.join(message_list)
            await interaction.response.send_message(message)

@bot.tree.command(name='voice', description='やっほー！から始まる音声を返します', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def yaho_voice(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get('https://mambouchan.com/hamahiyo/generate') as response:
            data = await response.json()
            message = data['message']
            message_list = re.split(r'[\t\n]', message)[:3]
            message = '\n'.join(message_list)

            audio_content = text_to_speech(message)

            with open('output.wav', 'wb') as f:
                f.write(audio_content)
            
            await interaction.response.send_message(file=File("output.wav"))

@bot.tree.command(name='prompt', description='指定した文章から文章を生成します', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def generate(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()  # デフォルトの応答を保留

    temperature, clean_prompt = extract_t_option(prompt)  # -tオプションを抽出

    try:
        message = f"**{clean_prompt}**" + n_messages_completion(clean_prompt, num=2, temperature=temperature).replace("\t", "\n")

        await interaction.followup.send(message)  # 非同期にフォローアップメッセージを送信
    except Exception as e:
        # エラーハンドリング
        await interaction.followup.send(f'An error occurred: {str(e)}')

# ボイスチャンネルに参加するコマンド
@bot.command(name='join', description='指定のボイスチャンネルに参加します', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def join_voice(ctx):
    if ctx.author.voice:  # コマンド実行者がボイスチャンネルにいるか確認
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f'{channel.name} に参加しました！')
    else:
        await ctx.send("ボイスチャンネルに接続していません！")

# ボイスチャンネルから退出するコマンド
@bot.command(name='leave', description='ボイスチャンネルから退出します', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def leave_voice(ctx):
    if ctx.voice_client:  # Botがボイスチャンネルに接続しているか確認
        await ctx.voice_client.disconnect()
        await ctx.send("ボイスチャンネルから退出しました。")
    else:
        await ctx.send("ボイスチャンネルに接続していません！")


@tasks.loop(hours=24)
async def daily_yaho():
    await bot.wait_until_ready()  # ボットが完全に準備されるのを待つ
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://mambouchan.com/hamahiyo/generate') as response:
                data = await response.json()
                message = data['message']
                message_list = re.split(r'[\t\n]', message)[:3]
                message = '\n'.join(message_list)
                await channel.send(message)

def schedule_daily_yaho():
    now = datetime.now()
    target_time = datetime.combine(now.date(), time(7, 0))
    if now > target_time:
        target_time += timedelta(days=1)
    wait_time = (target_time - now).total_seconds()
    asyncio.get_event_loop().call_later(wait_time, daily_yaho.start)


async def main():
    await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
    # print(extract_d_option("こんにちは -d"))

