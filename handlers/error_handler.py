import logging
import traceback
import html
from telegram import Update
from telegram.ext import ContextTypes
from config.settings import settings

logger = logging.getLogger(__name__)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a notification to logs channel/admin if configured."""
    logger.error("Exception while handling an update:", exc_info=context.error)

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    if settings.LOGS_CHANNEL:
        try:
            update_str = str(update) if update else "No update"
            message = (
                f"⚠️ <b>An error occurred</b>\n\n"
                f"<b>Update:</b>\n<code>{html.escape(update_str[:500])}</code>\n\n"
                f"<b>Error:</b>\n<code>{html.escape(str(context.error))}</code>\n\n"
                f"<b>Traceback:</b>\n<code>{html.escape(tb_string[-1500:])}</code>"
            )
            await context.bot.send_message(
                chat_id=settings.LOGS_CHANNEL,
                text=message,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send error notification to logs channel: {e}")
