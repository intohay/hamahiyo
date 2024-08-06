import os
import discord
import asyncio
from discord.ext import commands, tasks
from dotenv import load_dotenv
import requests
from datetime import datetime, time, timedelta


import aiohttp
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents)



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
            message_list = message.split('[SEP]')[:3]
            message = '\n\n'.join(message_list)
            await interaction.response.send_message(message)


@bot.tree.command(name='prompt', description='指定した文章から文章を生成します')
async def generate(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()  # デフォルトの応答を保留

    try:
        # gpt-2 を使う generate_messages をインポート
        from generate import generate_messages
        
        # メッセージを生成
        messages = generate_messages(prompt, max_length=64, num_sentences=1)
        message = messages[0]
        message_list = message.split('[SEP]')[:2]  # [SEP] 以降の文章を削除
        message = '\n'.join(message_list)
        # 先頭のpromptを**太字**にする
        message = message.replace(prompt, f'**{prompt}**', 1)
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
                message_list = message.split('[SEP]')[:3]
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

asyncio.run(main())
