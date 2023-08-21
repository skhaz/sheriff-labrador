import abc
import asyncio
import json
import os
from typing import Optional
from typing import TypedDict

from redis.asyncio import ConnectionPool
from redis.asyncio import Redis
from telegram import Update
from telegram.ext import Application
from telegram.ext import ContextTypes
from telegram.ext import MessageHandler
from telegram.ext import filters


class APIGatewayProxyEventV1(TypedDict):
    body: Optional[str]


class Context(metaclass=abc.ABCMeta):
    pass


pool = ConnectionPool.from_url(os.environ["REDIS_DSN"])
redis = Redis(connection_pool=pool)

application = (
    Application.builder().token(os.environ["TELEGRAM_TOKEN"]).updater(None).build()
)


async def on_enter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        print("no message!")
        return

    user = message.from_user
    if not user:
        print("no user!")
        return

    await asyncio.gather(
        message.reply_text("Hi!"),
        redis.set(f"telegram:{message.chat_id}:{user.id}", "1"),
    )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("on_message")
    print(update.to_json())
    message = update.message
    if not message:
        print("no message!")
        return

    user = message.from_user
    if not user:
        print("no user!")
        return

    x = await redis.incr("x")
    await message.reply_text(f"Hello {x}")
    # look on redis, if present, delete any message


async def on_leave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("on_leave")
    message = update.message
    if not message:
        print("no message!")
        return

    user = message.from_user
    if not user:
        print("no user!")
        return

    await message.reply_text("Bye")
    # remove the key from redis


application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_enter))
application.add_handler(MessageHandler(filters.CHAT, on_message))
application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_leave))


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
