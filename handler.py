import abc
import asyncio
import json
import multiprocessing
import os
import random
import string
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Optional
from typing import TypedDict

from redis.asyncio import ConnectionPool
from redis.asyncio import Redis
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application
from telegram.ext import CommandHandler
from telegram.ext import ContextTypes
from telegram.ext import MessageHandler
from telegram.ext import filters


class APIGatewayProxyEventV1(TypedDict):
    body: Optional[str]


class Context(metaclass=abc.ABCMeta):
    pass


application = (
    Application.builder().token(os.environ["TELEGRAM_TOKEN"]).updater(None).build()
)

pool = ConnectionPool.from_url(os.environ["REDIS_DSN"])
redis = Redis(connection_pool=pool)

executor = ThreadPoolExecutor(max_workers=multiprocessing.cpu_count())


async def on_enter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return

    user = message.from_user
    if not user:
        return

    cipher = "".join(random.sample(string.ascii_lowercase + string.digits, 4))
    text = f"In order for your entry to be accepted into the group, please respond with the following number: {cipher}"  # noqa
    await asyncio.gather(
        message.reply_text(text),
        redis.set(f"ciphers:{message.chat_id}:{user.id}", cipher),
    )


async def on_leave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return

    user = message.from_user
    if not user:
        return

    await asyncio.gather(
        message.reply_text("Bye"),
        redis.delete(f"ciphers:{message.chat_id}:{user.id}"),
    )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return

    user = message.from_user
    if not user:
        return

    cipher = await redis.get(f"ciphers:{message.chat_id}:{user.id}")

    if not cipher:
        return

    text = message.text

    if not text or cipher.decode().lower() != text.lower():
        try:
            await message.delete()
        except TelegramError:
            pass

        return

    await asyncio.gather(
        redis.delete(f"ciphers:{message.chat_id}:{user.id}"),
        message.reply_text("Welcome to the group!"),
    )


async def temp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    def func():
        return "Ok"

    result = await asyncio.get_event_loop().run_in_executor(executor, func)
    message = update.message
    if not message:
        return
    await message.reply_text(result)


application.add_handler(CommandHandler("temp", temp))
application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_enter))
application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_leave))
application.add_handler(
    MessageHandler(
        filters.ALL
        & ~filters.StatusUpdate.NEW_CHAT_MEMBERS
        & ~filters.StatusUpdate.LEFT_CHAT_MEMBER,
        on_message,
    )
)


async def main(event: APIGatewayProxyEventV1):
    body = event["body"]
    if not body:
        return

    async with application:
        await application.process_update(
            Update.de_json(json.loads(body), application.bot)
        )


def telegram(event: APIGatewayProxyEventV1, context: Context):
    asyncio.get_event_loop().run_until_complete(main(event))

    return {
        "statusCode": 200,
    }
