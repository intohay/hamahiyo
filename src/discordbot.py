import os
import discord
import asyncio
from discord.ext import commands, tasks
from dotenv import load_dotenv
import requests
from datetime import datetime, time, timedelta
import pdb
import re
from generate import completion
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


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await bot.tree.sync()
    schedule_daily_yaho()


@bot.tree.command(name='yaho', description='やほー！から始まる文章を返します')
async def yaho(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get('https://mambouchan.com/hamahiyo/generate') as response:
            data = await response.json()
            message = data['message']
            message_list = message.split('\t')[:3]
            message = '\n\n'.join(message_list)
            await interaction.response.send_message(message)



@bot.tree.command(name='prompt', description='指定した文章から文章を生成します')
async def generate(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()  # デフォルトの応答を保留

    try:
        message = f"**{prompt}**" + completion(prompt)
        await interaction.followup.send(message)  # 非同期にフォローアップメッセージを送信
    except Exception as e:
        # エラーハンドリング
        await interaction.followup.send(f'An error occurred: {str(e)}')


@tasks.loop(hours=24)
async def daily_yaho():
    await bot.wait_until_ready()  # ボットが完全に準備されるのを待つ
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://mambouchan.com/hamahiyo/generate') as response:
                data = await response.json()
                message = data['message']
                message_list = message.split('\t')[:3]
                message = '\n\n'.join(message_list)
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

