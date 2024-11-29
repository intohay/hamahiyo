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
from collections import defaultdict

import MeCab

mecab = MeCab.Tagger("-Ochasen")


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


def extract_phrases(text):
    """
    日本語の文章から形態解析を行い、意味のあるフレーズを抽出します。
    主に名詞句（名詞+助詞+名詞、形容詞+名詞など）を対象とします。
    """
    phrases = []
    node = mecab.parseToNode(text)
    current_phrase = []  # フレーズを一時的に保持するリスト

    while node:
        word = node.surface  # 単語の表層形
        feature = node.feature.split(",")  # 品詞情報

        if feature[0] in ["名詞", "形容詞"]:  # 名詞や形容詞ならフレーズを構成
            current_phrase.append(word)
        elif feature[0] == "助詞" and current_phrase:  # 助詞が続いたらフレーズを保持
            current_phrase.append(word)
        else:
            # 現在のフレーズを phrases に保存してリセット
            if current_phrase:
                phrases.append("".join(current_phrase))
                current_phrase = []
        
        node = node.next

    # 最後のフレーズを保存
    if current_phrase:
        phrases.append("".join(current_phrase))

    return phrases
    

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
    
    asyncio.create_task(run_daily_message())

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

            if message.reference is not None:
                reply_message = await message.channel.fetch_message(message.reference.message_id)
                if reply_message and reply_message.author != bot.user:
                    question = reply_message.content
                    message = reply_message
                    


            is_debug, question = extract_d_option(question)  # -dオプションを抽出
            temperature, question = extract_t_option(question)  # -tオプションを抽出


            if is_reply:

                current_message = message
                
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
                    
                    print(answer)
                    audio_content = await loop.run_in_executor(pool, text_to_speech, answer)

                    # print(audio_content)
            
                
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

    if interaction.guild.voice_client:
        vc = interaction.guild.voice_client

        loop = asyncio.get_event_loop()
        with concurrent.futures.ProcessPoolExecutor() as pool:
            audio_content = await loop.run_in_executor(pool, text_to_speech, message)

            audio_file_path = f"output_{interaction.id}.wav"

            with open(audio_file_path, 'wb') as f:
                f.write(audio_content)

            

            source = discord.FFmpegPCMAudio(audio_file_path)
            vc.play(source)

            while vc.is_playing():
                print('playing')
                await asyncio.sleep(1)

            os.remove(audio_file_path)
            print('done')

    else:
        await interaction.response.send_message("ボイスチャンネルにいないと読めないよ！")
        return

    
    

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

    
    if interaction.guild.voice_client:
        vc = interaction.guild.voice_client

        loop = asyncio.get_event_loop()
        with concurrent.futures.ProcessPoolExecutor() as pool:
            audio_content = await loop.run_in_executor(pool, text_to_speech, message)

            audio_file_path = f"output_{interaction.id}.wav"

            with open(audio_file_path, 'wb') as f:
                f.write(audio_content)

            

            source = discord.FFmpegPCMAudio(audio_file_path)
            vc.play(source)

            while vc.is_playing():
                print('playing')
                await asyncio.sleep(1)

            os.remove(audio_file_path)
            print('done')

    else:
        await interaction.response.send_message("ボイスチャンネルにいないと読めないよ！")
        return
    
# @bot.tree.command(name='readmulti', description='ランダムに複数のブログを読み上げます', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
# async def read_blogs(interaction: discord.Interaction, num: int = 1):

#     audio_files = [f for f in os.listdir('data') if f.endswith('.mp3')]
#     if len(audio_files) == 0:
#         await interaction.response.send_message("音声ファイルがまだないよ！")
#         return

#     audio_files = random.sample(audio_files, num)

#     urls = []
#     for audio_file in audio_files:
#         blog_id = audio_file.split('-')[-1].replace('.mp3', '')
#         date_str = audio_file.split('-')[0]
#         url = f"https://www.hinatazaka46.com/s/official/diary/detail/{blog_id}"

#         urls.append(url)

    
#     for url, audio_file in zip(urls, audio_files):
#         audio_file_path = f'data/{audio_file}'
#         if not os.path.exists(audio_file_path):
#             await interaction.response.send_message("音声ファイルがまだないよ！")
#             return

#         if interaction.guild.voice_client:
#             vc = interaction.guild.voice_client
#         else:
#             await interaction.response.send_message("ボイスチャンネルにいないと読めないよ！")
#             return
        
#         await interaction.response.send_message(f"読むね！{url}")

#         source = discord.FFmpegPCMAudio(audio_file_path)
#         vc.play(source)

#         while vc.is_playing():
#             print('playing')
#             await asyncio.sleep(1)

#         vc.stop()
#         print('done')
        
    

@bot.tree.command(name='echo', description='指定した文章を読み上げます', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def echo(interaction: discord.Interaction, text: str):

    await interaction.response.send_message(text)

    loop = asyncio.get_event_loop()

    with concurrent.futures.ProcessPoolExecutor() as pool:
        audio_content = await loop.run_in_executor(pool, text_to_speech, text)

        audio_file_path = f"output_{interaction.id}.wav"

        with open(audio_file_path, 'wb') as f:
            f.write(audio_content)

        if interaction.guild.voice_client:
            vc = interaction.guild.voice_client
        else:
            await interaction.response.send_message("ボイスチャンネルにいないと読めないよ！")
            return

        source = discord.FFmpegPCMAudio(audio_file_path)
        vc.play(source)

        while vc.is_playing():
            print('playing')
            await asyncio.sleep(1)

        os.remove(audio_file_path)
        print('done')

        






@bot.tree.command(name='read', description='指定したURLのブログを読み上げます', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def read_blog(interaction: discord.Interaction, url: str = None):
    
    url_template = "https://www.hinatazaka46.com/s/official/diary/detail/{}"

    if url is None:
        
        # data配下にあるmp3ファイルからランダムに選択して再生 
        audio_files = [f for f in os.listdir('data') if f.endswith('.mp3')]
        if len(audio_files) == 0:
            await interaction.response.send_message("音声ファイルがまだないよ！")
            return


        audio_file = random.choice(audio_files)

        

        audio_file_path = f'data/{audio_file}'
        # 2024-01-01-123456.mp3 の形式で保存されているので、123456の部分を抽出
        url = url_template.format(audio_file.split('-')[-1].replace('.mp3', ''))



    # URLが数字のみの場合、通し番号として扱う
    elif url.isdigit():
        # 通し番号なので、data配下のファイル名をソートして、その通し番号のファイルを再生
        audio_files = [f for f in os.listdir('data') if f.endswith('.mp3')]
        audio_files.sort()
        
        if int(url) > len(audio_files):
            await interaction.response.send_message("指定した番号の音声ファイルが存在しないよ！")
            return
        
        audio_file = audio_files[int(url) - 1]
        audio_file_path = f'data/{audio_file}'
        url = url_template.format(audio_file.split('-')[-1].replace('.mp3', ''))
        urls = [url]


    else:
        blog_id = re.search(r'detail/(\d+)', url).group(1)
        date_str = extract_date_from_blog(url)

        # data/{blog_id}.mp3 が存在するか確認
        audio_file_path = f'data/{date_str}-{blog_id}.mp3'
        urls = [url]




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
        
        await interaction.response.send_message(f"読むね！{url}")

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


def get_next_wait_time(mean: float, std_dev: float) -> float:
    """
    次の投稿までの時間を正規分布に基づいてサンプリング。
    負の値にならないよう、再サンプリングを実施。
    """
    wait_time = -1
    while wait_time <= 0:
        wait_time = random.gauss(mean, std_dev)
    return wait_time



async def run_daily_message():
    """
    ランダムな間隔で `daily_yaho` を実行し、次回の投稿時間をスケジュールする。
    """
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Channel with ID {CHANNEL_ID} not found.")
        return

    messages = []
    async for message in channel.history(limit=10):
        messages.append(message.content)

    if not messages:
        print("No messages found to generate a prompt.")
        return

    all_words = []
    for message in messages:
        all_words.extend(extract_phrases(message))
    
    if not all_words:
        print("No valid words found in recent messages.")
        return

    # 日本語のみを対象にする
    all_words = [word for word in all_words if re.match(r'^[ぁ-んァ-ン一-龥]', word)]


    selected_word = random.choice(all_words)
    print(f"Selected word for prompt: {selected_word}")

    prompt = f"{selected_word}"

    async with channel.typing():
        loop = asyncio.get_event_loop()
        with concurrent.futures.ProcessPoolExecutor() as pool:
            try:
                answer = await loop.run_in_executor(pool, retry_completion, prompt, 2, 1.2, 3, ["\t", "\n"])
                answer = answer.replace("\t", "\n")
                if not answer:
                    print("Failed to generate an answer.")
                    return
            except Exception as e:
                print(f"Error in generating response: {e}")
                return

    await channel.send(prompt + answer)

    # 次回の待機時間を計算（平均12時間、標準偏差4時間とする例）
    mean_hours = 6  # 平均時間（12時間）
    std_dev_hours = 3  # 標準偏差（4時間）
    next_wait_time_seconds = get_next_wait_time(mean_hours * 3600, std_dev_hours * 3600)

    print(f"Next daily_yaho will run in {next_wait_time_seconds / 3600:.2f} hours.")
    # 次回の投稿をスケジュール
    await asyncio.sleep(next_wait_time_seconds)
    await run_daily_message()



async def main():
    await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    
    asyncio.run(main())
    

