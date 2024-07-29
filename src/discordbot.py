import os
import discord
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
import requests


load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
# CHANNEL_ID = int(os.getenv('CHANNEL_ID'))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')


@bot.command(name='yaho')
async def yaho(ctx):
    # https://mambouchan.com/hamahiyo/generateにリクエストを送る
    response = requests.get('https://mambouchan.com/hamahiyo/generate')
    message = response.json()['message']
    await ctx.send(f"やほー！\n{message}")


@bot.command(name='prompt')
async def generate(ctx, *, prompt):
    from generate import generate_messages
    messages = generate_messages(prompt, num_sentences=1, num_messages=2)
    await ctx.send(messages[0][0])

async def main():
    await bot.start(DISCORD_TOKEN)

asyncio.run(main())
