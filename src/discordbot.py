import asyncio
import base64
import concurrent.futures
import json
import os
import random
import re
import time
from datetime import datetime, timedelta, timezone
from io import BytesIO

import aiohttp
import discord
import requests
from discord.ext import commands
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image
from transformers import AutoTokenizer

from message_timing_model import MessageTimingModel
from utilities import contains_bad_words

load_dotenv()

RUNPOD_LLAMA_ENDPOINT_ID = os.getenv("RUNPOD_LLAMA_ENDPOINT_ID")
RUNPOD_VITS_ENDPOINT_ID = os.getenv("RUNPOD_VITS_ENDPOINT_ID")
RUNPOD_BASE_URL = os.getenv("RUNPOD_BASE_URL")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
RUNPOD_VITS_URL = (
    f"{RUNPOD_BASE_URL}/{RUNPOD_VITS_ENDPOINT_ID}/runsync"
    if RUNPOD_BASE_URL and RUNPOD_VITS_ENDPOINT_ID
    else None
)

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))


# モデル切り替え用グローバル変数
USE_OPENAI_MODEL = True
OPENAI_MODEL = "ft:gpt-4o-2024-08-06:personal:hamahiyo:BMYosJsB"

# daily messageタスクの管理用グローバル変数
daily_message_task = None

# dailyメッセージの当日初回判定用（日跨ぎで文脈を切るため、返信等は無関係）
last_daily_message_date = None

# 次回予定時刻（「平均6h/標準偏差4h」ポスト）
next_scheduled_post_at = None

# 直近の1時間チェックの基準刻み
last_hourly_check_at = None

# メッセージタイミングモデル
timing_model = None

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)


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
tokenizer = AutoTokenizer.from_pretrained(
    "tokyotech-llm/Llama-3.1-Swallow-8B-Instruct-v0.3"
)

# 投稿ロジックの調整用定数（環境変数で上書き可）
HOURLY_INTERACTION_PROB = float(os.getenv("HOURLY_INTERACTION_PROB", "0.35"))
MEAN_POST_INTERVAL_HOURS = float(os.getenv("MEAN_POST_INTERVAL_HOURS", "6"))
STD_POST_INTERVAL_HOURS = float(os.getenv("STD_POST_INTERVAL_HOURS", "4"))


# 画像をリサイズする関数
def resize_image_if_needed(image_data, max_size=(1024, 1024), quality=85):
    """
    画像が大きすぎる場合にリサイズします
    """
    try:
        # PILで画像を開く
        image = Image.open(BytesIO(image_data))

        # 元のサイズをチェック
        if image.width <= max_size[0] and image.height <= max_size[1]:
            return image_data  # リサイズ不要

        # アスペクト比を保持してリサイズ
        image.thumbnail(max_size, Image.Resampling.LANCZOS)

        # JPEG形式で保存（品質を調整してファイルサイズを削減）
        output = BytesIO()
        image_format = "JPEG" if image.mode == "RGB" else "PNG"
        if image_format == "JPEG":
            image.save(output, format=image_format, quality=quality, optimize=True)
        else:
            image.save(output, format=image_format, optimize=True)

        resized_data = output.getvalue()
        print(f"Image resized from {len(image_data)} to {len(resized_data)} bytes")
        return resized_data

    except Exception as e:
        print(f"Error resizing image: {e}")
        return image_data  # リサイズに失敗した場合は元のデータを返す


# 画像をダウンロードしてbase64エンコードする関数
async def download_and_encode_image(attachment, max_file_size_mb=10):
    """
    Discord添付ファイルをダウンロードしてbase64エンコードします
    """
    try:
        # 画像ファイルかどうかチェック
        if not attachment.content_type or not attachment.content_type.startswith(
            "image/"
        ):
            return None

        # ファイルサイズチェック
        if attachment.size > max_file_size_mb * 1024 * 1024:
            print(
                f"Image too large: {attachment.size / (1024 * 1024):.1f}MB > {max_file_size_mb}MB"
            )
            return None

        # 画像をダウンロード
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as response:
                if response.status == 200:
                    image_data = await response.read()

                    # 画像をリサイズ（必要に応じて）
                    image_data = resize_image_if_needed(image_data)

                    # base64エンコード
                    encoded_image = base64.b64encode(image_data).decode("utf-8")
                    return encoded_image, attachment.content_type
                else:
                    print(f"Failed to download image: {response.status}")
                    return None
    except Exception as e:
        print(f"Error downloading image: {e}")
        return None


# メッセージから画像を取得する関数
async def get_images_from_message(message, max_images=3):
    """
    Discordメッセージから画像を取得してbase64エンコードします
    """
    images = []
    if message.attachments:
        for attachment in message.attachments:
            if len(images) >= max_images:
                print(f"Image limit reached ({max_images}), skipping remaining images")
                break

            image_result = await download_and_encode_image(attachment)
            if image_result:
                images.append(image_result)
                print(f"Image detected: {attachment.filename}")
    return images


# メッセージの内容を画像も含めて構築する関数
def build_message_content(text_content, images):
    """
    テキストと画像を含むメッセージコンテンツを構築します
    """
    if not images:
        return text_content

    content = [{"type": "text", "text": text_content}]
    for encoded_image, content_type in images:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{content_type};base64,{encoded_image}"},
            }
        )
    return content


# OpenAI APIを使用した応答生成
async def generate_openai_response(prompt=None, temperature=0.8, conversation=None):
    try:
        # 会話履歴がある場合はそれを使用し、ない場合は単一のプロンプトを使用
        if conversation:
            messages = [
                {"role": "system", "content": get_system_prompt()}
            ] + conversation
        else:
            messages = [
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": prompt},
            ]

        for _ in range(3):
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL, messages=messages, temperature=temperature
            )
            content = response.choices[0].message.content
            if not contains_bad_words(content):
                return content

        return "生成が失敗しました。もう一度試してください。"
    except Exception as e:
        print(f"OpenAI API error: {e}")
        return "エラーが発生しました。もう一度試してください。"


async def generate_runpod_response(prompt=None, temperature=0.8, conversation=None):
    url = f"{RUNPOD_BASE_URL}/{RUNPOD_LLAMA_ENDPOINT_ID}/runsync"

    headers = {
        "Authorization": f"Bearer {RUNPOD_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        if conversation:
            messages = [
                {"role": "system", "content": get_system_prompt()}
            ] + conversation
        else:
            messages = [
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": prompt},
            ]

        print(messages)

        payload = {
            "input": {
                "messages": messages,
                # vLLMネイティブのsampling_paramsに細かく指定 (https://github.com/runpod-workers/worker-vllm?tab=readme-ov-file#openai-request-input-parameters)
                "sampling_params": {
                    "temperature": temperature,
                    "top_p": 0.9,
                    "top_k": 50,
                    "repetition_penalty": 1.1,
                },
                "stream": False,
            }
        }

        for _ in range(3):

            def extract_text_from_response(response_json):
                """RunPodの様々なレスポンス形式からテキストを安全に取り出す。"""
                try:
                    # 既存のvLLMトークナイズ出力形式
                    return response_json["output"][0]["choices"][0]["tokens"][0]
                except Exception:
                    pass

                output = response_json.get("output")

                # ステータスAPIの形式 { output: { text: [...]|str, ... } }
                if isinstance(output, dict):
                    if "text" in output:
                        text_val = output["text"]
                        if isinstance(text_val, list):
                            return "".join(text_val)
                        return str(text_val)
                    # OpenAI風 { output: { choices: [ { message: { content } } ] } }
                    if (
                        "choices" in output
                        and isinstance(output["choices"], list)
                        and output["choices"]
                    ):
                        choice = output["choices"][0]
                        if isinstance(choice, dict):
                            if (
                                "message" in choice
                                and isinstance(choice["message"], dict)
                                and "content" in choice["message"]
                            ):
                                return str(choice["message"]["content"])
                            if "text" in choice:
                                return str(choice["text"])

                # OpenAI互換がトップレベルにあるケース
                if (
                    "choices" in response_json
                    and isinstance(response_json["choices"], list)
                    and response_json["choices"]
                ):
                    choice = response_json["choices"][0]
                    if isinstance(choice, dict):
                        if (
                            "message" in choice
                            and isinstance(choice["message"], dict)
                            and "content" in choice["message"]
                        ):
                            return str(choice["message"]["content"])
                        if "text" in choice:
                            return str(choice["text"])

                return None

            r = requests.post(url, headers=headers, json=payload, timeout=600)
            r.raise_for_status()
            data = r.json()
            print(data)

            # IN_QUEUE の場合はステータスAPIをポーリング
            if data.get("status") == "IN_QUEUE" and data.get("id"):
                job_id = data["id"]
                status_url = (
                    f"{RUNPOD_BASE_URL}/{RUNPOD_LLAMA_ENDPOINT_ID}/status/{job_id}"
                )
                while True:
                    try:
                        sr = requests.get(status_url, headers=headers, timeout=600)
                        sr.raise_for_status()
                        sdata = sr.json()
                        print(sdata)

                        s = sdata.get("status")
                        if s == "COMPLETED":
                            content = extract_text_from_response(sdata)
                            if content is None:
                                content = json.dumps(sdata)
                            if not contains_bad_words(content):
                                return content.replace("\t", "\n").split("\n")[0]
                            else:
                                break  # 次の試行へ
                        elif s in {"FAILED", "ERROR", "CANCELLED", "TIMED_OUT"}:
                            # 異常終了は次の試行へ
                            break
                    except Exception as _:
                        # 一時的なエラーはリトライ
                        pass
                    await asyncio.sleep(1)

            # 通常の同期レスポンスから抽出
            content = extract_text_from_response(data)
            if content is None:
                content = json.dumps(data)

            if not contains_bad_words(content):
                return content.replace("\t", "\n").split("\n")[0]

        return "生成が失敗しました。もう一度試してください。"

    except Exception as e:
        print(f"RunPod API error: {e}")
        return "エラーが発生しました。もう一度試してください。"


def fetch_audio_from_api(text):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {RUNPOD_API_KEY}",
    }
    data = {
        "input": {
            "action": "/voice",
            "model_id": 1,
            "text": text,
        }
    }

    response = requests.post(RUNPOD_VITS_URL, headers=headers, data=json.dumps(data))
    print(response.json())
    if response.status_code != 200:
        raise Exception(f"API call failed with status code {response.status_code}")

    resp_json = response.json()

    def extract_voice_from_response(resp_obj):
        try:
            output = resp_obj.get("output")
            if isinstance(output, dict):
                # 期待形式: { output: { voice: "...base64..." } }
                if "voice" in output:
                    return output["voice"]
                # 代替形式: { output: { audio: "..." } }
                if "audio" in output:
                    return output["audio"]
        except Exception:
            pass
        return None

    # IN_QUEUE の場合はステータスAPIでポーリング
    if resp_json.get("status") == "IN_QUEUE" and resp_json.get("id"):
        job_id = resp_json["id"]
        status_url = f"{RUNPOD_BASE_URL}/{RUNPOD_VITS_ENDPOINT_ID}/status/{job_id}"
        while True:
            try:
                sr = requests.get(status_url, headers=headers, timeout=600)
                sr.raise_for_status()
                sdata = sr.json()
                print(sdata)
                s = sdata.get("status")
                if s == "COMPLETED":
                    voice_b64 = extract_voice_from_response(sdata)
                    if voice_b64:
                        return voice_b64
                    # フォールバック: 形が違う場合は例外
                    raise Exception("Voice data not found in completed response")
                elif s in {"FAILED", "ERROR", "CANCELLED", "TIMED_OUT"}:
                    raise Exception(f"VITS job ended with status: {s}")
            except Exception as _:
                # 一時的なエラーは待機して再試行
                pass
            time.sleep(1)

    # 通常の同期レスポンスから抽出
    voice_b64 = extract_voice_from_response(resp_json)
    if voice_b64:
        return voice_b64

    raise Exception("Unexpected VITS response format: voice not found")


def save_audio_file(base64_data, file_path):
    audio_data = base64.b64decode(base64_data)
    with open(file_path, "wb") as file:
        file.write(audio_data)


def text_to_speech(text: str, file_path: str):
    base64_audio = fetch_audio_from_api(text)
    save_audio_file(base64_audio, file_path)


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
    t_option_pattern = r"-t\s+([0-9]*\.?[0-9]+)"
    t_option_match = re.search(t_option_pattern, prompt)

    if t_option_match:
        t_value = float(t_option_match.group(1))  # -t の数値を float で抽出
        clean_prompt = re.sub(
            t_option_pattern, "", prompt
        ).strip()  # -tオプション部分を削除
    else:
        t_value = default_value  # デフォルト値を使用
        clean_prompt = prompt.strip()  # オプションが無い場合もクリーンアップ

    return t_value, clean_prompt


# -dオプションを抽出するための関数(デバッグ用)
def extract_d_option(prompt: str):
    d_option_pattern = r"-d"
    d_option_match = re.search(d_option_pattern, prompt)

    if d_option_match:
        # -dオプションを取り除く
        clean_prompt = re.sub(d_option_pattern, "", prompt).strip()

        return True, clean_prompt

    return False, prompt


@bot.event
async def on_ready():
    global daily_message_task, timing_model

    print(f"Logged in as {bot.user.name}")
    await bot.tree.sync(guild=discord.Object(id=int(os.getenv("GUILD_ID"))))
    print(f"{bot.user.name} is connected to the following guilds:")
    for guild in bot.guilds:
        print(f"{guild.name} (id: {guild.id})")

    voice_channel = bot.get_channel(int(os.getenv("VOICE_CHANNEL_ID")))
    if len(voice_channel.members) > 0:
        await voice_channel.connect()
        print("Bot reconnected to the voice channel.")

    # メッセージタイミングモデルを初期化
    try:
        timing_model = MessageTimingModel()
        timing_model.print_model_info()
        print("Message timing model loaded successfully.")
    except Exception as e:
        print(f"Failed to load timing model: {e}")
        timing_model = None

    # daily messageタスクが既に実行中でないかチェック
    if daily_message_task is None or daily_message_task.done():
        daily_message_task = asyncio.create_task(run_daily_message())
        print("Daily message task started.")
    else:
        print("Daily message task is already running.")


@bot.event
async def on_voice_state_update(member, before, after):
    # 参加するのが自分でないことを確認
    if member.bot:
        return

    # ユーザーが指定のチャンネルに参加した場合
    voice_channel = bot.get_channel(int(os.getenv("VOICE_CHANNEL_ID")))
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


async def handle_generating_and_converting(message: discord.Message):
    if message.author == bot.user:
        return

    is_mention = bot.user.mentioned_in(message)
    is_reply = (
        message.reference is not None and message.reference.resolved.author == bot.user
    )

    # Botがメンションされたかどうか確認
    if is_mention or is_reply:
        # typing...を表示
        async with message.channel.typing():
            # メンションを削除
            question = message.content.replace(f"<@{bot.user.id}>", "").strip()

            # botに聞いてなかった質問を後から質問にしたい場合
            if message.reference is not None:
                reply_message = await message.channel.fetch_message(
                    message.reference.message_id
                )
                if reply_message and reply_message.author != bot.user:
                    question = reply_message.content
                    message = reply_message

            is_debug, question = extract_d_option(question)  # -dオプションを抽出
            temperature, question = extract_t_option(question)  # -tオプションを抽出

            # 現在のメッセージから画像を取得
            images = await get_images_from_message(message)

            conversation = None

            # リプライの場合
            if is_reply:
                chat = [{"role": "system", "content": get_system_prompt()}]
                # 現在のメッセージ（質問）から画像も含めて内容を構築
                current_question_content = build_message_content(question, images)
                conversation = [{"role": "user", "content": current_question_content}]
                current_message = message
                all_images = images.copy()  # すべての画像を追跡

                # 過去の履歴を取得し、会話履歴を作成
                while current_message.reference is not None:
                    previous_message = await current_message.channel.fetch_message(
                        current_message.reference.message_id
                    )
                    previous_answer = previous_message.content

                    conversation = [
                        {"role": "assistant", "content": previous_answer}
                    ] + conversation

                    if previous_message.reference:
                        more_previous_message = (
                            await current_message.channel.fetch_message(
                                previous_message.reference.message_id
                            )
                        )
                        previous_question = more_previous_message.content.replace(
                            f"<@{bot.user.id}>", ""
                        ).strip()

                        # 前の質問メッセージから画像も取得（制限あり）
                        if len(all_images) < 5:  # 全体で最大5枚まで
                            remaining_slots = 5 - len(all_images)
                            previous_images = await get_images_from_message(
                                more_previous_message, max_images=remaining_slots
                            )
                            all_images.extend(previous_images)

                        # 画像も含めて前の質問内容を構築
                        previous_question_content = build_message_content(
                            previous_question, previous_images
                        )

                        conversation = [
                            {"role": "user", "content": previous_question_content}
                        ] + conversation

                        current_message = more_previous_message

                    # トークン数チェック（簡易版）
                    try:
                        prompt = tokenizer.apply_chat_template(
                            chat + conversation,
                            tokenize=True,
                            add_generation_prompt=True,
                        )
                        if len(prompt) > 250:
                            break
                    except Exception:
                        # 画像が含まれている場合、トークン計算が失敗する可能性があるので、
                        # 会話の長さで制限
                        if len(conversation) > 10:
                            break

                    if previous_message.reference is None:
                        break

                # 画像がリプライチェーンに含まれている場合、OpenAIを強制使用
                if all_images and not USE_OPENAI_MODEL:
                    print(
                        "Images found in reply chain, switching to OpenAI for this response"
                    )
            # メンションの場合
            else:
                # 現在のメッセージから画像も含めて内容を構築
                question_content = build_message_content(question, images)
                conversation = [{"role": "user", "content": question_content}]
                chat = [{"role": "system", "content": get_system_prompt()}]

                # 画像がない場合のみトークン計算
                if not images:
                    prompt = tokenizer.apply_chat_template(
                        chat + conversation, tokenize=True, add_generation_prompt=True
                    )

            # 画像の有無を判定（現在のメッセージまたはリプライチェーン内）
            has_images = bool(images) or (is_reply and bool(all_images))

            if USE_OPENAI_MODEL or has_images:
                # OpenAI APIを使用（画像がある場合は強制的にOpenAI）
                if has_images and not USE_OPENAI_MODEL:
                    print("Images detected, switching to OpenAI for this response")

                # 画像処理はgenerate_openai_response内で行われるため、imagesパラメータは不要
                answer = await generate_openai_response(
                    conversation=conversation,
                    temperature=temperature,
                )
            else:
                # RunPodを使用（画像がない場合のみ）
                answer = await generate_runpod_response(
                    conversation=conversation, temperature=temperature
                )

            # ボイスチャンネルにいる場合は音声生成を試行
            if (
                message.guild.voice_client
                and message.author.voice
                and message.author.voice.channel
            ):
                loop = asyncio.get_event_loop()
                with concurrent.futures.ProcessPoolExecutor() as pool:
                    audio_file_path = f"output_{message.id}.wav"
                    try:
                        await loop.run_in_executor(
                            pool, text_to_speech, answer, audio_file_path
                        )

                        # メッセージを送信してから音声を再生
                        await message.reply(answer)

                        # 音声をボイスチャンネルで再生
                        vc = message.guild.voice_client
                        source = discord.FFmpegPCMAudio(audio_file_path)
                        vc.play(source)

                        while vc.is_playing():
                            print("playing")
                            await asyncio.sleep(1)

                        os.remove(audio_file_path)  # 一時ファイルを削除
                    except Exception as e:
                        # 音声生成に失敗してもメッセージは送信
                        await message.reply(answer)
                        await message.channel.send(f"音声生成エラー: {str(e)}")
            else:
                await message.reply(answer)


@bot.tree.command(name="yaho", description="やほー！から始まる文章を返します")
async def yaho(interaction: discord.Interaction):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://mambouchan.com/hamahiyo/generate") as response:
            data = await response.json()
            message = data["message"]
            message_list = re.split(r"[\t\n]", message)[:3]
            message = "\n".join(message_list)
            await interaction.response.send_message(message)

    if interaction.guild.voice_client:
        vc = interaction.guild.voice_client

        loop = asyncio.get_event_loop()
        with concurrent.futures.ProcessPoolExecutor() as pool:
            audio_file_path = f"output_{interaction.id}.wav"
            try:
                await loop.run_in_executor(
                    pool, text_to_speech, message, audio_file_path
                )
            except Exception as e:
                await interaction.followup.send(f"An error occurred: {str(e)}")
                return

            source = discord.FFmpegPCMAudio(audio_file_path)
            vc.play(source)

            while vc.is_playing():
                print("playing")
                await asyncio.sleep(1)

            os.remove(audio_file_path)
            print("done")

    else:
        await interaction.response.send_message(
            "ボイスチャンネルにいないと読めないよ！"
        )
        return


# @bot.tree.command(name="prompt", description="指定した文章から文章を生成します")
# async def generate(interaction: discord.Interaction, prompt: str):
#     await interaction.response.defer()  # デフォルトの応答を保留

#     temperature, clean_prompt = extract_t_option(prompt)  # -tオプションを抽出

#     try:

#             chat = [{"role": "system", "content": get_system_prompt()}]
#             template_applied_prompt = tokenizer.apply_chat_template(
#                 chat, add_generation_prompt=True, tokenize=True
#             ) + tokenizer.encode(clean_prompt, add_special_tokens=False)

#             while True:
#                 completion = n_messages_completion(
#                     template_applied_prompt, num=2, temperature=temperature
#                 ).replace("\t", "\n")
#                 if not contains_bad_words(completion):
#                     message = f"**{clean_prompt}**" + completion
#                     break
#         await interaction.followup.send(
#             message
#         )  # 非同期にフォローアップメッセージを送信
#     except Exception as e:
#         # エラーハンドリング
#         await interaction.followup.send(f"An error occurred: {str(e)}")

#     if interaction.guild.voice_client:
#         vc = interaction.guild.voice_client

#         loop = asyncio.get_event_loop()
#         with concurrent.futures.ProcessPoolExecutor() as pool:
#             audio_file_path = f"output_{interaction.id}.wav"
#             try:
#                 await loop.run_in_executor(pool, text_to_speech, message, audio_file_path)
#             except Exception as e:
#                 await interaction.followup.send(f"An error occurred: {str(e)}")
#                 return

#             source = discord.FFmpegPCMAudio(audio_file_path)
#             vc.play(source)

#             while vc.is_playing():
#                 print("playing")
#                 await asyncio.sleep(1)

#             os.remove(audio_file_path)
#             print("done")

#     else:
#         await interaction.followup.send("ボイスチャンネルにいないと読めないよ！")
#         return


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


@bot.tree.command(
    name="echo",
    description="指定した文章を読み上げます",
    guild=discord.Object(id=int(os.getenv("GUILD_ID"))),
)
async def echo(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text)

    loop = asyncio.get_event_loop()

    with concurrent.futures.ProcessPoolExecutor() as pool:
        audio_file_path = f"output_{interaction.id}.wav"

        await loop.run_in_executor(pool, text_to_speech, text, audio_file_path)

        if interaction.guild.voice_client:
            vc = interaction.guild.voice_client
        else:
            await interaction.response.send_message(
                "ボイスチャンネルにいないと読めないよ！"
            )
            return

        source = discord.FFmpegPCMAudio(audio_file_path)
        vc.play(source)

        while vc.is_playing():
            print("playing")
            await asyncio.sleep(1)

        os.remove(audio_file_path)
        print("done")


@bot.tree.command(
    name="speech",
    description="卒業セレモニーのスピーチを読み上げます",
    guild=discord.Object(id=int(os.getenv("GUILD_ID"))),
)
async def speech(interaction: discord.Interaction):
    await interaction.response.send_message("卒業セレモニーのスピーチを読むね！")

    audio_file_path = "data/speech.mp3"

    if not os.path.exists(audio_file_path):
        await interaction.response.send_message("音声ファイルがまだないよ！")
        return

    if interaction.guild.voice_client:
        vc = interaction.guild.voice_client
    else:
        await interaction.response.send_message(
            "ボイスチャンネルにいないと読めないよ！"
        )
        return

    source = discord.FFmpegPCMAudio(audio_file_path)
    vc.play(source)

    while vc.is_playing():
        print("playing")
        await asyncio.sleep(1)
    print("done")


@bot.tree.command(
    name="read",
    description="指定したURLのブログを読み上げます",
    guild=discord.Object(id=int(os.getenv("GUILD_ID"))),
)
async def read_blog(interaction: discord.Interaction, url: str = None):
    if url is None:
        # data配下にあるmp3ファイルからランダムに選択して再生
        audio_files = [f for f in os.listdir("data") if f.endswith(".mp3")]
        if len(audio_files) == 0:
            await interaction.response.send_message("音声ファイルがまだないよ！")
            return

        audio_file = random.choice(audio_files)

        audio_file_path = f"data/{audio_file}"

    # URLが数字のみの場合、通し番号として扱う
    elif url.isdigit():
        # 通し番号なので、data配下のファイル名をソートして、その通し番号のファイルを再生
        audio_files = [f for f in os.listdir("data") if f.endswith(".mp3")]
        audio_files.sort()

        if int(url) > len(audio_files):
            await interaction.response.send_message(
                "指定した番号の音声ファイルが存在しないよ！"
            )
            return

        audio_file = audio_files[int(url) - 1]
        audio_file_path = f"data/{audio_file}"

    if not os.path.exists(audio_file_path):
        # 存在しない場合、その旨を返信
        await interaction.response.send_message("音声ファイルがまだないよ！")
        return
    else:
        # 存在する場合、botがボイスチャンネルに接続して、接続している場合は再生
        # 接続していない場合は、ボイスチャンネルに接続する旨を返信
        if interaction.guild.voice_client:
            vc = interaction.guild.voice_client
        else:
            await interaction.response.send_message(
                "ボイスチャンネルにいないと読めないよ！"
            )
            return

        await interaction.response.send_message("読むね！")

        source = discord.FFmpegPCMAudio(audio_file_path)
        vc.play(source)

        # 再生が完了するまで待機
        while vc.is_playing():
            print("playing")
            await asyncio.sleep(1)
        print("done")


@bot.tree.command(
    name="sing",
    description="指定した番号の歌を歌います",
    guild=discord.Object(id=int(os.getenv("GUILD_ID"))),
)
async def sing(interaction: discord.Interaction, num: int = None):
    # data/songsの中のmp3とm4aのファイル名(拡張子なし)を取得
    songs = [f for f in os.listdir("songs") if f.endswith((".mp3", ".m4a"))]
    songs.sort()  # アルファベット順にソート

    # numが指定されていない場合はその一覧をインデックスとともに返す
    if num is None:
        song_list = "\n".join(
            [f"{i + 1}: {os.path.splitext(song)[0]}" for i, song in enumerate(songs)]
        )
        await interaction.response.send_message(f"歌う歌を選んでね！\n{song_list}")
        return

    # numが指定されている場合、その番号の歌を歌う
    if num > len(songs):
        await interaction.response.send_message("指定した番号の歌が存在しないよ！")
        return

    song = songs[num - 1]
    audio_file_path = f"songs/{song}"

    if not os.path.exists(audio_file_path):
        await interaction.response.send_message("音声ファイルがまだないよ！")
        return

    if interaction.guild.voice_client:
        vc = interaction.guild.voice_client
    else:
        await interaction.response.send_message(
            "ボイスチャンネルにいないと歌えないよ！"
        )
        return

    await interaction.response.send_message(
        f"『{os.path.splitext(song)[0]}』を歌うね！"
    )

    source = discord.FFmpegPCMAudio(audio_file_path)
    vc.play(source)

    while vc.is_playing():
        print("playing")
        await asyncio.sleep(1)
    print("done")


# ボイスチャンネルに参加するコマンド
@bot.tree.command(
    name="join",
    description="指定のボイスチャンネルに参加します",
    guild=discord.Object(id=int(os.getenv("GUILD_ID"))),
)
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
            await interaction.response.send_message(f"{channel.name}に遊びに来たよ！")
        else:
            await interaction.response.send_message(
                "ボイスチャンネルに接続してから呼んでね！"
            )
    except Exception as e:
        print(e)

    # ボイスチャンネルから退出するコマンド


@bot.tree.command(
    name="leave",
    description="ボイスチャンネルから退出します",
    guild=discord.Object(id=int(os.getenv("GUILD_ID"))),
)
async def leave_voice(interaction: discord.Interaction):
    if interaction.guild.voice_client:  # Botがボイスチャンネルに接続しているか確認
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("ばいころまる〜")
    else:
        await interaction.response.send_message("ボイスチャンネルに接続していないよ！")


# モデル切り替えコマンド
@bot.tree.command(
    name="switch_model",
    description="使用するモデルを切り替えます",
    guild=discord.Object(id=int(os.getenv("GUILD_ID"))),
)
async def switch_model(interaction: discord.Interaction):
    global USE_OPENAI_MODEL
    USE_OPENAI_MODEL = not USE_OPENAI_MODEL

    model_name = (
        "OpenAI API (ファインチューニング版)"
        if USE_OPENAI_MODEL
        else "Llama-3.1-Swallow"
    )
    await interaction.response.send_message(
        f"モデルを「{model_name}」に切り替えました！"
    )


# 現在のモデルを確認するコマンド
@bot.tree.command(
    name="current_model",
    description="現在使用しているモデルを表示します",
    guild=discord.Object(id=int(os.getenv("GUILD_ID"))),
)
async def current_model(interaction: discord.Interaction):
    model_name = (
        "OpenAI API (ファインチューニング版)"
        if USE_OPENAI_MODEL
        else "Llama-3.1-Swallow"
    )
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
    シンプルな投稿ロジック:
      - 24時間いつでも投稿可
      - 文脈は当日分のみ（自分=assistant/他人=user）
      - 毎日最低1回はランダムな時刻に投稿
      - 1時間ごとに他人のメッセージがあれば確率的に投稿
      - 別に平均6h/標準偏差4hの投稿も並行して実施
      - 当日の初回は「やほー！」から生成
    """
    global last_daily_message_date, next_scheduled_post_at, last_hourly_check_at

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print(f"Channel with ID {CHANNEL_ID} not found.")
        return

    jst = timezone(timedelta(hours=9))

    # 次回のランダムスケジュール（平均/分散）を初期化
    now = datetime.now(jst)
    if next_scheduled_post_at is None:
        next_scheduled_post_at = now + timedelta(
            hours=get_next_wait_time(MEAN_POST_INTERVAL_HOURS, STD_POST_INTERVAL_HOURS)
        )

    # 当日最低1回の必須投稿時刻を設定
    def make_today_mandatory_time(base_now):
        start_of_day = base_now.replace(hour=0, minute=0, second=0, microsecond=0)
        seconds = random.randint(0, 24 * 60 * 60 - 1)
        return start_of_day + timedelta(seconds=seconds)

    today = now.date()
    daily_mandatory_post_at = make_today_mandatory_time(now)

    # 起動時は必ず一度、文脈なし（やほー！）で投稿
    try:
        startup_conversation = [{"role": "assistant", "content": "やほー！"}]
        async with channel.typing():
            answer = await generate_runpod_response(
                conversation=startup_conversation, temperature=1.1
            )
            answer = answer.replace("\t", "\n")
            if "やほー" not in answer:
                answer = "やほー！\n" + answer
            await channel.send(answer)
            print(f"Startup message sent: {answer[:50]}...")

            # 当日初回として記録し、次回スケジュールも更新
            last_daily_message_date = today
            next_scheduled_post_at = now + timedelta(
                hours=get_next_wait_time(
                    MEAN_POST_INTERVAL_HOURS, STD_POST_INTERVAL_HOURS
                )
            )
    except Exception as e:
        print(f"Error sending startup message: {e}")

    while True:
        try:
            now = datetime.now(jst)
            today = now.date()

            # 日付が変わったら初回判定と必須投稿時刻をリセット
            if last_daily_message_date != today:
                daily_mandatory_post_at = make_today_mandatory_time(now)

            # 1時間ごとのチェック判定（同じ時間帯で一度だけ）
            hourly_trigger = False
            if (
                last_hourly_check_at is None
                or last_hourly_check_at.astimezone(jst).hour != now.hour
                or last_hourly_check_at.astimezone(jst).date() != today
            ):
                # 直近1時間に他人メッセージがあるか
                one_hour_ago = now - timedelta(hours=1)
                others_exist = False
                async for m in channel.history(limit=200, after=one_hour_ago):
                    if m.author != bot.user:
                        others_exist = True
                        break

                if others_exist and random.random() < HOURLY_INTERACTION_PROB:
                    hourly_trigger = True

                last_hourly_check_at = now

            # 次のスケジュール投稿の時刻を満たしたか
            scheduled_trigger = next_scheduled_post_at and now >= next_scheduled_post_at

            # 当日の初回投稿がまだで、必須投稿時刻を過ぎたか
            is_first_post_of_day = last_daily_message_date != today
            mandatory_trigger = is_first_post_of_day and now >= daily_mandatory_post_at

            should_post = mandatory_trigger or scheduled_trigger or hourly_trigger

            if should_post:
                # 当日のメッセージを会話として構築
                conversation = []
                total_tokens = 0
                TOKEN_LIMIT = 350

                # 初回は「やほー！」のみを文脈に
                if is_first_post_of_day:
                    conversation = [{"role": "assistant", "content": "やほー！"}]
                else:
                    # 当日分を古い→新しい順で積み上げ
                    day_messages = []
                    async for m in channel.history(limit=500):
                        if not m.content:
                            continue
                        msg_date = m.created_at.astimezone(jst).date()
                        if msg_date == today:
                            day_messages.append(m)
                        else:
                            # 以前の日が見えたら打ち切り（履歴が時系列降順のため）
                            break

                    for m in reversed(day_messages):  # 古い順に
                        message_tokens = len(tokenizer.encode(m.content))
                        if total_tokens + message_tokens > TOKEN_LIMIT:
                            break
                        role = "assistant" if m.author == bot.user else "user"
                        conversation.append({"role": role, "content": m.content})
                        total_tokens += message_tokens

                # 生成
                async with channel.typing():
                    try:
                        answer = await generate_runpod_response(
                            conversation=conversation, temperature=1.1
                        )
                        answer = answer.replace("\t", "\n")

                        if not answer:
                            print("Failed to generate an answer.")
                            await asyncio.sleep(60)
                            continue

                        # 初回は先頭にやほー！を保証
                        if is_first_post_of_day and "やほー" not in answer:
                            answer = "やほー！\n" + answer

                        await channel.send(answer)
                        print(f"Message sent: {answer[:50]}...")

                        # 状態更新
                        last_daily_message_date = today
                        # 次のスケジュール時刻を再サンプル
                        next_scheduled_post_at = now + timedelta(
                            hours=get_next_wait_time(
                                MEAN_POST_INTERVAL_HOURS, STD_POST_INTERVAL_HOURS
                            )
                        )

                    except Exception as e:
                        print(f"Error in generating response: {e}")
                        await asyncio.sleep(60)

            # 次のループまで待機（シンプルに1分）
            await asyncio.sleep(60)

        except Exception as e:
            print(f"Error in run_daily_message: {e}")
            await asyncio.sleep(120)


async def main():
    await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
