import abc
import asyncio
import json
import os
import random
from typing import Optional
from typing import TypedDict

from redis.asyncio import ConnectionPool
from redis.asyncio import Redis
from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application
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


async def on_enter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return

    user = message.from_user
    if not user:
        return

    cipher = random.randint(0, 10)
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

    if not text or cipher.decode() not in text:
        try:
            await message.delete()
        except TelegramError:
            pass

        return

    await asyncio.gather(
        redis.delete(f"ciphers:{message.chat_id}:{user.id}"),
        message.reply_text("Welcome to the group!"),
    )


application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_enter))
application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_leave))
application.add_handler(
    MessageHandler(
        filters.ALL
        & filters.Document.ALL
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
