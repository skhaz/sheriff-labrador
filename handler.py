import abc
import asyncio
import json
import logging
import os
import random
import re
import string
from datetime import datetime
from typing import Dict
from typing import Optional
from typing import TypedDict
from urllib.parse import urlencode

import aioboto3
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application
from telegram.ext import ContextTypes
from telegram.ext import MessageHandler
from telegram.ext import filters


class APIGatewayProxyEventV1(TypedDict):
    headers: Dict[str, str]
    body: Optional[str]


class Context(metaclass=abc.ABCMeta):
    pass


application = (
    Application.builder().token(os.environ.get("TELEGRAM_TOKEN")).updater(None).build()
)

boto3 = aioboto3.Session()

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

ignore = re.compile("^Message to delete not found$")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if not error:
        return

    logger.error("Exception while handling an update:", exc_info=error)

    if not isinstance(update, Update):
        return

    if isinstance(error, BadRequest):
        message = error.message

        if ignore.match(message):
            return

        chat = update.effective_chat

        if not chat:
            return

        text = f"Howl... I need to be an admin in order to work properly (privilege to delete messages)\.\n\n`{message}`"  # noqa

        await context.bot.send_message(
            chat_id=chat.id,
            text=text,
            parse_mode=ParseMode.MARKDOWN_V2,
        )


async def on_enter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return

    async with boto3.resource("dynamodb") as dynamodb:
        table = await dynamodb.Table(os.environ["DYNAMODB_TABLE"])
        async with table.batch_writer() as batch:
            for user in message.new_chat_members:
                if not user:
                    continue

                if user.is_bot:
                    continue

                cipher = "".join(random.sample(string.ascii_uppercase, 4))
                url = "?".join([os.environ["ENDPOINT"], urlencode({"text": cipher})])
                caption = "Woof! In order for your entry to be accepted into the group, please answer the captcha."  # noqa

                response = await message.reply_photo(url, caption=caption)

                await batch.put_item(
                    Item={
                        "id": f"{message.chat_id}:{user.id}",
                        "ttl": int(datetime.now().timestamp()) + 60**2,
                        "cipher": cipher,
                        "chat_id": str(message.chat_id),
                        "message_id": str(response.id),
                        "join_id": str(message.id),
                        "user_id": str(user.id),
                    }
                )


async def on_leave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return

    user = message.left_chat_member
    if not user:
        return

    if user.is_bot:
        return

    key = {"id": f"{message.chat_id}:{user.id}"}

    async with boto3.resource("dynamodb") as dynamodb:
        table = await dynamodb.Table(os.environ["DYNAMODB_TABLE"])
        response = await table.get_item(Key=key)
        item = response.get("Item")
        if not item:
            return

        await asyncio.gather(
            context.bot.delete_message(
                chat_id=message.chat_id, message_id=item["message_id"]
            ),
            context.bot.delete_message(
                chat_id=message.chat_id, message_id=item["join_id"]
            ),
            message.delete(),
            table.delete_item(Key=key),
        )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return

    user = message.from_user
    if not user:
        return

    key = {"id": f"{message.chat_id}:{user.id}"}

    async with boto3.resource("dynamodb") as dynamodb:
        table = await dynamodb.Table(os.environ["DYNAMODB_TABLE"])
        response = await table.get_item(Key=key)

        item = response.get("Item")
        if not item:
            return

        cipher = item.get("cipher")
        if not cipher:
            return

        text = message.text
        if not text or cipher != re.sub(r"\s+", "", text).upper():
            await message.delete()
            return

        await asyncio.gather(
            context.bot.delete_message(
                chat_id=message.chat_id,
                message_id=item["message_id"],
            ),
            context.bot.delete_message(
                chat_id=message.chat_id,
                message_id=item["join_id"],
            ),
            table.delete_item(Key=key),
            message.delete(),
        )

        user = message.from_user
        if not user:
            return

        mention = f"[{user.username}](tg://user?id={user.id})"

        await context.bot.send_message(
            message.chat_id,
            f"{mention}, welcome to the group\! Au\!",
            parse_mode=ParseMode.MARKDOWN_V2,
        ),


application.add_error_handler(error_handler)
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


def equals(left, right):
    if not left or not right:
        return False

    if len(left) != len(right):
        return False

    for c1, c2 in zip(left, right):
        if c1 != c2:
            return False

    return True


def telegram(event: APIGatewayProxyEventV1, context: Context):
    if not equals(
        event["headers"].get("x-telegram-bot-api-secret-token"),
        os.environ["SECRET"],
    ):
        return {
            "statusCode": 401,
        }

    asyncio.get_event_loop().run_until_complete(main(event))

    return {
        "statusCode": 200,
    }


def stream(event, context: Context):
    promises = []
    bot = application.bot
    loop = asyncio.get_event_loop()

    for record in event["Records"]:
        image = record["dynamodb"]["OldImage"]
        promises.extend(
            [
                bot.delete_message(
                    chat_id=image["chat_id"]["S"],
                    message_id=image["message_id"]["S"],
                ),
                bot.unban_chat_member(
                    chat_id=image["chat_id"]["S"],
                    user_id=image["user_id"]["S"],
                ),
                bot.delete_message(
                    chat_id=image["chat_id"]["S"],
                    message_id=image["join_id"]["S"],
                ),
            ]
        )

    loop.run_until_complete(asyncio.gather(*promises))
