import os
import discord
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
import requests

import aiohttp
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
# CHANNEL_ID = int(os.getenv('CHANNEL_ID'))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents)



@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await bot.tree.sync()


@bot.tree.command(name='yaho', description='やほー！から始まる文章を返します')
async def yaho(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get('https://mambouchan.com/hamahiyo/generate') as response:
            data = await response.json()
            message = data['message']
            await interaction.response.send_message(f"やほー！\n{message}")


@bot.tree.command(name='prompt', description='指定した文章から文章を生成します')
async def generate(interaction: discord.Interaction, prompt: str):
    await interaction.response.defer()  # デフォルトの応答を保留

    try:
        # gpt-2 を使う generate_messages をインポート
        from generate import generate_messages
        
        # メッセージを生成
        messages = generate_messages(prompt, num_sentences=1, num_messages=2)
        message = messages[0][0]
        
        # 先頭のpromptを**太字**にする
        message = message.replace(prompt, f'**{prompt}**', 1)
        await interaction.followup.send(message)  # 非同期にフォローアップメッセージを送信
    except Exception as e:
        # エラーハンドリング
        await interaction.followup.send(f'An error occurred: {str(e)}')

async def main():
    await bot.start(DISCORD_TOKEN)

asyncio.run(main())
