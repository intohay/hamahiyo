import os
import discord
import asyncio
from discord.ext import commands, tasks
from dotenv import load_dotenv
import requests
from datetime import datetime, time, timedelta, timezone
import pdb
import re
from discord import File
from generate import n_messages_completion, tokenize, text_to_speech, retry_completion
import aiohttp
from utilities import contains_bad_words, extract_name_from_blog, scrape_blog, extract_date_from_blog
from reading import text_to_audio
import aiohttp
import random
from collections import defaultdict
from transformers import AutoTokenizer
from openai import OpenAI




openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

runpod_client = OpenAI(base_url="https://api.runpod.ai/v2/a24s38kbwrbmgt/openai/v1", api_key=os.getenv("RUNPOD_API_KEY"))

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))


# モデル切り替え用グローバル変数
USE_OPENAI_MODEL = True
OPENAI_MODEL = "ft:gpt-4o-2024-08-06:personal:hamahiyo:BMYosJsB"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents)

import unicodedata

def normalize_text(text):
    # 全角と半角を統一
    return unicodedata.normalize('NFKC', text)

# モデルごとのシステムプロンプト
LLAMA_SYSTEM_PROMPT = "あなたは「ハマヒヨちゃん」というキャラクターです。一人称は「私」または「ヒヨタン」を使い、それ以外使わないで下さい。"
OPENAI_SYSTEM_PROMPT = "あなたは「ハマヒヨちゃん」というキャラクターです。一人称は「ヒヨタン」または「私」に限定し、「ヒヨタン」は一人称としてのみ使用すること。"

# システムプロンプトを取得する関数
def get_system_prompt():
    if USE_OPENAI_MODEL:
        return OPENAI_SYSTEM_PROMPT
    else:
        return LLAMA_SYSTEM_PROMPT

system_prompt = get_system_prompt()
tokenizer = AutoTokenizer.from_pretrained("tokyotech-llm/Llama-3.1-Swallow-8B-Instruct-v0.3")



# -tオプションを抽出するための関数
def extract_t_option(prompt: str, default_value: float = 1.1):
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

# OpenAI APIを使用した応答生成
async def generate_openai_response(prompt=None, temperature=0.8, conversation=None):
    
    try:
        # 会話履歴がある場合はそれを使用し、ない場合は単一のプロンプトを使用
        if conversation:
            messages = [{"role": "system", "content": get_system_prompt()}] + conversation
        else:
            messages = [
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": prompt}
            ]
        
        print(messages)
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=temperature
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return "エラーが発生しました。もう一度試してください。"

async def generate_runpod_response(prompt=None, temperature=0.8, conversation=None):
    try:
        if conversation:
            messages = [{"role": "system", "content": get_system_prompt()}] + conversation
        else:
            messages = [
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": prompt}
            ]
        
        print(messages)
        response = runpod_client.chat.completions.create(
            model="intohay/llama3.1-swallow-hamahiyo",
            messages=messages,
            temperature=temperature,
        )
        
        print(response)
        return response.choices[0].message.content
    except Exception as e:
        print(f"RunPod API error: {e}")
        return "エラーが発生しました。もう一度試してください。"

async def handle_generating_and_converting(message: discord.Message):
    if message.author == bot.user:
        return

    is_mention = bot.user.mentioned_in(message)
    is_reply = message.reference is not None and message.reference.resolved.author == bot.user

    # Botがメンションされたかどうか確認
    if is_mention or is_reply:
        async with message.channel.typing():
            # メンションされたら応答
            question = message.content.replace(f'<@{bot.user.id}>', '').strip()
            
            # botに聞いてなかった質問を後から質問にしたい場合
            if message.reference is not None:
                reply_message = await message.channel.fetch_message(message.reference.message_id)
                if reply_message and reply_message.author != bot.user:
                    question = reply_message.content
                    message = reply_message
                    
            is_debug, question = extract_d_option(question)  # -dオプションを抽出
            temperature, question = extract_t_option(question)  # -tオプションを抽出

            conversation = None
            
            if is_reply:
                chat = [{"role": "system", "content": get_system_prompt()}]
                conversation = [{"role": "user", "content": question}]
                current_message = message
                
                while current_message.reference is not None:
                    previous_message = await current_message.channel.fetch_message(current_message.reference.message_id)
                    previous_answer = previous_message.content

                    conversation = [{"role": "assistant", "content": previous_answer}] + conversation

                    if previous_message.reference:
                        more_previous_message = await current_message.channel.fetch_message(previous_message.reference.message_id)
                        previous_question = more_previous_message.content.replace(f'<@{bot.user.id}>', '').strip()

                        conversation = [{"role": "user", "content": previous_question}] + conversation

                        current_message = more_previous_message

                    prompt = tokenizer.apply_chat_template(chat + conversation, tokenize=True, add_generation_prompt=True)

                    if len(prompt) > 250:
                        break

                    if previous_message.reference is None:
                        break
            else:
                conversation = [{"role": "user", "content": question}]
                chat = [{"role": "system", "content": get_system_prompt()}]
                prompt = tokenizer.apply_chat_template(chat + conversation, tokenize=True, add_generation_prompt=True)

            # if message.guild.voice_client and message.author.voice and message.author.voice.channel:
                # loop = asyncio.get_event_loop()
                # with concurrent.futures.ProcessPoolExecutor() as pool:
                #     if USE_OPENAI_MODEL:
                #         answer = await generate_openai_response(conversation=conversation, temperature=temperature)
                #     else:
                #         answer = await loop.run_in_executor(pool, retry_completion, prompt, 1, temperature, 3, ["\n", "\t"])

                #     audio_content = await loop.run_in_executor(pool, text_to_speech, answer)
            
                #     audio_file_path = f"output_{message.id}.wav"
                    
                #     # 音声ファイルを保存
                #     with open(audio_file_path, 'wb') as f:
                #         f.write(audio_content)

                #     # 音声をボイスチャンネルで再生
                #     vc = message.guild.voice_client
                #     source = discord.FFmpegPCMAudio(audio_file_path)
                #     vc.play(source)
                
                #     while vc.is_playing():
                #         print('playing')
                #         # 現在の再生時間を計算
                #         await asyncio.sleep(1)  # 1秒ごとにチェック
                
                #     os.remove(audio_file_path)  # 一時ファイルを削除
                #     await message.reply(answer)
            # else:
                # loop = asyncio.get_event_loop()
                # with concurrent.futures.ProcessPoolExecutor() as pool:
                #     if USE_OPENAI_MODEL:
                #         answer = await generate_openai_response(conversation=conversation, temperature=temperature)
                #     else:
                #         answer = await loop.run_in_executor(pool, retry_completion, prompt, 1, temperature, 3, ["\t"])
                #     await message.reply(answer)
            
            if USE_OPENAI_MODEL:
                answer = await generate_openai_response(conversation=conversation, temperature=temperature)
            else:
                answer = await generate_runpod_response(conversation=conversation, temperature=temperature)
                answer = answer.replace("\t", "\n")
                answer = answer.split("\n")
                answer = answer[0]
                
            await message.reply(answer)

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

    
    



@bot.tree.command(name='prompt', description='指定した文章から文章を生成します')
async def generate(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()  # デフォルトの応答を保留

    temperature, clean_prompt = extract_t_option(prompt)  # -tオプションを抽出

    try:
        if USE_OPENAI_MODEL:
            message = f"**{clean_prompt}**" + await generate_openai_response(clean_prompt, temperature)
        else:
            chat = [{"role": "system", "content": get_system_prompt()}]
            template_applied_prompt = tokenizer.apply_chat_template(chat, add_generation_prompt=True, tokenize=True) + tokenizer.encode(clean_prompt, add_special_tokens=False)

            while True:
                completion = n_messages_completion(template_applied_prompt, num=2, temperature=temperature).replace("\t", "\n")
                if not contains_bad_words(completion):
                    message = f"**{clean_prompt}**" + completion
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
        await interaction.followup.send("ボイスチャンネルにいないと読めないよ！")
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

        




@bot.tree.command(name='speech', description='卒業セレモニーのスピーチを読み上げます', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def speech(interaction: discord.Interaction):
    await interaction.response.send_message("卒業セレモニーのスピーチを読むね！")

    audio_file_path = 'data/speech.mp3'

    if not os.path.exists(audio_file_path):
        await interaction.response.send_message("音声ファイルがまだないよ！")
        return

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

@bot.tree.command(name='sing', description='指定した番号の歌を歌います', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def sing(interaction: discord.Interaction, num: int = None):
    # data/songsの中のmp3とm4aのファイル名(拡張子なし)を取得
    songs = [f for f in os.listdir('songs') if f.endswith(('.mp3', '.m4a'))]
    songs.sort()  # アルファベット順にソート

    # numが指定されていない場合はその一覧をインデックスとともに返す
    if num is None:
        song_list = '\n'.join([f"{i+1}: {os.path.splitext(song)[0]}" for i, song in enumerate(songs)])
        await interaction.response.send_message(f"歌う歌を選んでね！\n{song_list}")
        return

    # numが指定されている場合、その番号の歌を歌う
    if num > len(songs):
        await interaction.response.send_message("指定した番号の歌が存在しないよ！")
        return

    song = songs[num - 1]
    audio_file_path = f'songs/{song}'

    if not os.path.exists(audio_file_path):
        await interaction.response.send_message("音声ファイルがまだないよ！")
        return

    if interaction.guild.voice_client:
        vc = interaction.guild.voice_client
    else:
        await interaction.response.send_message("ボイスチャンネルにいないと歌えないよ！")
        return

    await interaction.response.send_message(f"『{os.path.splitext(song)[0]}』を歌うね！")

    source = discord.FFmpegPCMAudio(audio_file_path)
    vc.play(source)

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


# モデル切り替えコマンド
@bot.tree.command(name='switch_model', description='使用するモデルを切り替えます', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def switch_model(interaction: discord.Interaction):
    global USE_OPENAI_MODEL
    USE_OPENAI_MODEL = not USE_OPENAI_MODEL
    
    model_name = "OpenAI API (ファインチューニング版)" if USE_OPENAI_MODEL else "Llama-3.1-Swallow"
    system_prompt = get_system_prompt()
    await interaction.response.send_message(f"モデルを「{model_name}」に切り替えました！")

# 現在のモデルを確認するコマンド
@bot.tree.command(name='current_model', description='現在使用しているモデルを表示します', guild=discord.Object(id=int(os.getenv('GUILD_ID'))))
async def current_model(interaction: discord.Interaction):
    model_name = "OpenAI API (ファインチューニング版)" if USE_OPENAI_MODEL else "Llama-3.1-Swallow"
    await interaction.response.send_message(f"現在のモデルは「{model_name}」です！")



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
    メッセージ履歴を文脈として使用し、その続きとしてメッセージを生成する。
    トークン数の制限（350トークン）を考慮して履歴を制限する。
    その日の最初の投稿の場合は「やほー！」を文脈の一部として含めて生成し、実際の投稿にも含める。
    新しいメッセージを優先的に保持し、古いメッセージは必要に応じて捨てる。
    """
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Channel with ID {CHANNEL_ID} not found.")
        return

    # メッセージ履歴を取得（最大20件まで取得）
    messages = []
    async for message in channel.history(limit=20):
        messages.append(message)

    if not messages:
        print("No messages found to generate a prompt.")
        return

    # 今日の日付を取得（JST）
    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst).date()
    print(f"Today (JST): {today}")

    # 最後の投稿が今日かどうかを確認
    is_first_post_of_day = True
    for message in messages:
        if message.author == bot.user:
            # メッセージの時刻をJSTに変換
            message_date = message.created_at.astimezone(jst).date()
            print(f"Message date: {message_date}, Message time: {message.created_at.astimezone(jst)}")
            if message_date == today:
                is_first_post_of_day = False
                break

    print(f"Is first post of day: {is_first_post_of_day}")

    # メッセージ履歴を会話形式に変換し、トークン数に基づいて制限
    conversation = []
    total_tokens = 0
    TOKEN_LIMIT = 350

    # システムプロンプトのトークン数を計算
    system_tokens = len(tokenizer.encode(get_system_prompt()))
    total_tokens += system_tokens

    # 新しい順に処理（messagesは新しい順に並んでいる）
    for message in messages:
        # メッセージのトークン数を計算
        message_tokens = len(tokenizer.encode(message.content))
        
        # トークン制限を超える場合は処理を終了
        if total_tokens + message_tokens > TOKEN_LIMIT:
            break

        # 会話履歴に追加（新しい順に追加）
        if message.author == bot.user:
            conversation.insert(0, {"role": "assistant", "content": message.content})
        else:
            conversation.insert(0, {"role": "user", "content": message.content})
        
        total_tokens += message_tokens

    print(f"Total tokens used: {total_tokens}")

    # システムプロンプトを追加
    chat = [{"role": "system", "content": get_system_prompt()}] + conversation

    # その日の最初の投稿の場合は「やほー！」を追加
    if is_first_post_of_day:
        chat.append({"role": "assistant", "content": "やほー！"})

    print(chat)
    async with channel.typing():
        loop = asyncio.get_event_loop()
        with concurrent.futures.ProcessPoolExecutor() as pool:
            try:
                # 会話履歴を使用して生成
                # if USE_OPENAI_MODEL:
                #     # OpenAI用にチャット履歴を整形
                    
                    
                #     response = openai_client.chat.completions.create(
                #         model=OPENAI_MODEL,
                #         messages=chat,
                #         temperature=1.2
                #     )
                #     answer = response.choices[0].message.content
                # else:
                
                # prompt = tokenizer.apply_chat_template(chat, tokenize=True, add_generation_prompt=True)
                # answer = await loop.run_in_executor(pool, retry_completion, prompt, 2, 1.2, 3, ["\t", "\n"])
                # answer = answer.replace("\t", "\n")
                
                answer = await generate_runpod_response(conversation=chat, temperature=0.8)
                answer = answer.replace("\t", "\n")
                
                
                if not answer:
                    print("Failed to generate an answer.")
                    return

                # その日の最初の投稿の場合は「やほー！」を追加
                if is_first_post_of_day and "やほー" not in answer:
                    answer = "やほー！\n" + answer

            except Exception as e:
                print(f"Error in generating response: {e}")
                return

    await channel.send(answer)

    # 次回の待機時間を計算（平均6時間、標準偏差3時間）
    mean_hours = 6
    std_dev_hours = 3
    next_wait_time_seconds = get_next_wait_time(mean_hours * 3600, std_dev_hours * 3600)

    print(f"Next daily_yaho will run in {next_wait_time_seconds / 3600:.2f} hours.")
    # 次回の投稿をスケジュール
    await asyncio.sleep(next_wait_time_seconds)
    await run_daily_message()



async def main():
    await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    
    asyncio.run(main())
    


