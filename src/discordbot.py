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
from utilities import contains_bad_words, extract_name_from_blog, scrape_blog, extract_date_from_blog
from reading import text_to_audio
import aiohttp
import random
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
            if answer and answer != "" and not contains_bad_words(answer):
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
    
    voice_channel = bot.get_channel(int(os.getenv('VOICE_CHANNEL_ID')))
    if len(voice_channel.members) > 0:
        await voice_channel.connect()
        print("Bot reconnected to the voice channel.")
    
    schedule_daily_yaho()

@bot.event
async def on_voice_state_update(member, before, after):
    
    # 参加するのが自分でないことを確認
    if member.bot:
        return

    # ユーザーが指定のチャンネルに参加した場合
    voice_channel = bot.get_channel(int(os.getenv('VOICE_CHANNEL_ID')))
    if after.channel == voice_channel and len(voice_channel.members) > 0:
        # ボットがまだボイスチャンネルにいない場合、参加する
        if bot.user not in voice_channel.members:
            await voice_channel.connect()
            print("Bot has joined the voice channel.")

                
           
    
    # 指定のチャンネルが空になった場合、ボットが退出する
    elif before.channel == voice_channel and len(voice_channel.members) == 1:
        # ボットが現在参加中であるかを確認
        if bot.voice_clients:
            await bot.voice_clients[0].disconnect()
            print("Bot has left the voice channel.")

            


@bot.event
async def on_message(message: discord.Message):
    asyncio.create_task(handle_generating_and_converting(message))

import concurrent.futures

async def handle_generating_and_converting(message: discord.Message):
    if message.author == bot.user:
        return

    is_mention = bot.user.mentioned_in(message)
    is_reply = message.reference is not None and message.reference.resolved.author == bot.user

    # トークン数カウント用の関数
    def get_token_count(text):
        return len(tokenize(text))
    
    # Botがメンションされたかどうか確認
    if is_mention or is_reply:
        async with message.channel.typing():
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
            
            
            # print(answer)

        

            if message.guild.voice_client and message.author.voice and message.author.voice.channel:
                

                loop = asyncio.get_event_loop()
                with concurrent.futures.ProcessPoolExecutor() as pool:
                    answer = await loop.run_in_executor(pool, retry_completion, prompt, 1, temperature, 3, ["\n", "\t", "Q:"])
                    audio_content = await loop.run_in_executor(pool, text_to_speech, answer)
            
            
                
                    audio_file_path = f"output_{message.id}.wav"
                    

                    # 音声ファイルを保存
                    with open(audio_file_path, 'wb') as f:
                        f.write(audio_content)

                    # 音声をボイスチャンネルで再生
                    vc = message.guild.voice_client
                    source = discord.FFmpegPCMAudio(audio_file_path)
                    vc.play(source)
                

                    while vc.is_playing():
                        print('playing')
                        # 現在の再生時間を計算
                        await asyncio.sleep(1)  # 1秒ごとにチェック
                
                    

                    os.remove(audio_file_path)  # 一時ファイルを削除
                    await message.reply(answer)
            else:
                loop = asyncio.get_event_loop()
                with concurrent.futures.ProcessPoolExecutor() as pool:
                    answer = await loop.run_in_executor(pool, retry_completion, prompt, 1, temperature, 3, ["\t", "Q:"])
                    await message.reply(answer)
            # メッセージにリプライ
            

@bot.tree.command(name='yaho', description='やほー！から始まる文章を返します')
async def yaho(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get('https://mambouchan.com/hamahiyo/generate') as response:
            data = await response.json()
            message = data['message']
            message_list = re.split(r'[\t\n]', message)[:3]
            message = '\n'.join(message_list)
            await interaction.response.send_message(message)

# 危険な感じがするのでコメントアウト
# @bot.tree.command(name='voice', description='やっほー！から始まる音声を返します', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
# async def yaho_voice(interaction: discord.Interaction):
#     # 応答を保留
#     await interaction.response.defer()

#     async with aiohttp.ClientSession() as session:
#         async with session.get('https://mambouchan.com/hamahiyo/generate') as response:
#             data = await response.json()
#             message = data['message']
#             message_list = re.split(r'[\t\n]', message)[:3]
#             message = '\n'.join(message_list)
#             # 「やほ」を「やっほ」に変換
#             message = message.replace('やほ', 'やっほ')

#             # テキストを音声に変換
#             audio_content = text_to_speech(message)

#             # 音声ファイルを一時保存
#             with open('output.wav', 'wb') as f:
#                 f.write(audio_content)
            
#             # followupで音声ファイルを送信
#             await interaction.followup.send(file=File("output.wav"))


@bot.tree.command(name='prompt', description='指定した文章から文章を生成します')
async def generate(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()  # デフォルトの応答を保留

    temperature, clean_prompt = extract_t_option(prompt)  # -tオプションを抽出

    try:
        while True:
            completion = n_messages_completion(clean_prompt, num=2, temperature=temperature).replace("\t", "\n")
            if not contains_bad_words(completion):
                message = f"**{clean_prompt}**" + n_messages_completion(clean_prompt, num=2, temperature=temperature).replace("\t", "\n")
                break
        await interaction.followup.send(message)  # 非同期にフォローアップメッセージを送信
    except Exception as e:
        # エラーハンドリング
        await interaction.followup.send(f'An error occurred: {str(e)}')

@bot.tree.command(name='read', description='指定したURLのブログを読み上げます', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def read_blog(interaction: discord.Interaction, url: str = None):
    # https://www.hinatazaka46.com/s/official/diary/detail/57856?ima=0000&cd=member
    # から57856を抽出
    
    if url is None:
        # data配下にあるmp3ファイルからランダムに選んで再生
        audio_files = [f for f in os.listdir('data') if f.endswith('.mp3')]
        if len(audio_files) == 0:
            await interaction.response.send_message("音声ファイルがまだないよ！")
            return
       
        audio_file = random.choice(audio_files)
        audio_file_path = f'data/{audio_file}'

    # URLが数字のみの場合、通し番号として扱う
    elif url.isdigit():
        # 通し番号なので、data配下のファイル名をソートして、その通し番号のファイルを再生
        audio_files = [f for f in os.listdir('data') if f.endswith('.mp3')]
        audio_files.sort()
        print(audio_files)
        audio_file_path = f'data/{audio_files[int(url) - 1]}'
    else:
        blog_id = re.search(r'detail/(\d+)', url).group(1)
        date_str = extract_date_from_blog(url)

        # data/{blog_id}.mp3 が存在するか確認
        audio_file_path = f'data/{date_str}-{blog_id}.mp3'

  


    if not os.path.exists(audio_file_path):
        #　存在しない場合、その旨を返信
        await interaction.response.send_message("音声ファイルがまだないよ！")
        return
    else:
        # 存在する場合、botがボイスチャンネルに接続して、接続している場合は再生
        # 接続していない場合は、ボイスチャンネルに接続する旨を返信
        if interaction.guild.voice_client:
            vc = interaction.guild.voice_client
        else:
            await interaction.response.send_message("ボイスチャンネルにいないと読めないよ！")
            return
        
        await interaction.response.send_message("読むね！")

        source = discord.FFmpegPCMAudio(audio_file_path)
        vc.play(source)

        # 再生が完了するまで待機
        while vc.is_playing():
            print('playing')
            await asyncio.sleep(1)
        print('done')


@bot.tree.command(name='convert', description='指定したURLのブログを音声に変換します', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def convert_blog(interaction: discord.Interaction, url: str):

    name = extract_name_from_blog(url)
    if name != "濱岸 ひより":
        await interaction.response.send_message("ひよたんのブログ以外は読まないよ！")
        return
    
    blog_id = re.search(r'detail/(\d+)', url).group(1)
    date_str = extract_date_from_blog(url)

    file_path = f'data/{date_str}-{blog_id}.mp3'

    if os.path.exists(file_path):
        await interaction.response.send_message("音声ファイルがすでにあるよ！")
        return
    

    await interaction.response.defer()  # デフォルトの応答を保留


    blog_text = await asyncio.to_thread(scrape_blog, url)

 
    await asyncio.to_thread(text_to_audio, blog_text, file_path)

    await interaction.followup.send("読む準備ができたよ！")

    

# ボイスチャンネルに参加するコマンド
@bot.tree.command(name='join', description='指定のボイスチャンネルに参加します', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def join_voice(interaction: discord.Interaction):
    try:
        # すでにボットがボイスチャンネルに接続しているか確認
        if interaction.guild.voice_client:
            await interaction.response.send_message("もうボイスチャンネルにいるよ！")
            return

        # コマンド実行者がボイスチャンネルにいるか確認
        if interaction.user.voice:
            channel = interaction.user.voice.channel
            await channel.connect()
            await interaction.response.send_message(f'{channel.name}に遊びに来たよ！')
        else:
            await interaction.response.send_message("ボイスチャンネルに接続してから呼んでね！")
    except Exception as e:
        print(e)

    # ボイスチャンネルから退出するコマンド
@bot.tree.command(name='leave', description='ボイスチャンネルから退出します', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def leave_voice(interaction: discord.Interaction):
    if interaction.guild.voice_client:  # Botがボイスチャンネルに接続しているか確認
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("ばいころまる〜")
    else:
        await interaction.response.send_message("ボイスチャンネルに接続していないよ！")

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
    

