import asyncio
import json
import os
from dataclasses import dataclass

from redis import ConnectionPool
from redis import Redis
from telegram import Update
from telegram.ext import Application
from telegram.ext import CallbackContext
from telegram.ext import ContextTypes
from telegram.ext import ExtBot
from telegram.ext import MessageHandler
from telegram.ext import filters


@dataclass
class WebhookUpdate:
    user_id: int
    payload: str


class CustomContext(CallbackContext[ExtBot, dict, dict, dict]):
    @classmethod
    def from_update(
        cls,
        update: object,
        application: "Application",
    ) -> "CustomContext":
        if isinstance(update, WebhookUpdate):
            return cls(application=application, user_id=update.user_id)
        return super().from_update(update, application)


redis_pool = ConnectionPool.from_url(os.environ["REDIS_DSN"])
redis = Redis(connection_pool=redis_pool)

context_types = ContextTypes(context=CustomContext)
application = (
    Application.builder()
    .token(os.environ["TELEGRAM_TOKEN"])
    .updater(None)
    .context_types(context_types)
    .build()
)


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(update.message.text)


application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))


async def main(event):
    async with application:
        await application.process_update(
            Update.de_json(json.loads(event["body"]), application.bot)
        )

def telegram(event, context):
    asyncio.run(main(event))

    return {
        "statusCode": 200,
    }
