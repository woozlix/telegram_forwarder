import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler
)
from config import logger, get_config
import db

SOURCE, DESTINATION = range(2)

MSG_HELP_ID_SOURCE = """
<b>Перешлите сообщение</b> из канала источника (откуда пересылать сообщения) или <b>введите ID группы источника</b> (пример: -1002719997220).\n
Взять ID группы можно в версии Telegram Web в адресной строке.
Например, если группа https://web.telegram.org/k/#-2844913382, то после знака '-' добавляем 100, получится: -1002844913382.
"""
MSG_HELP_ID_DESTINATION = """
<b>Перешлите сообщение</b> из канала назначения (куда пересылать сообщения) или <b>введите ID группы назначения</b> (пример: -1002719997220).\n
Взять ID группы можно в версии Telegram Web в адресной строке.
Например, если группа https://web.telegram.org/k/#-2844913382, то после знака '-' добавляем 100, получится: -1002844913382.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in whitelist_ids:
        return
    await update.message.reply_text(
        f'Привет {update.effective_user.first_name}!\n\n'
        f'Чтобы бот мог пересылать сообщения, он должен быть админом в группе/канале источника и в группе/канале назначения.\n\n'
        f'Доступные команды:\n\n'
        f'/start - информация о боте\n'
        f'/add - добавить пересылку сообщений\n'
        f'/list - показать ваши подписки\n'
        f'/remove - удалить подписку'
        f'/cancel - отменить действие'
    )


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id not in whitelist_ids:
        return ConversationHandler.END

    await update.message.reply_text(
        MSG_HELP_ID_SOURCE,
        parse_mode='HTML',
        disable_web_page_preview=True
    )
    return SOURCE


async def source_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.forward_from_chat:
        context.user_data['source_id'] = str(update.message.forward_from_chat.id)
        await update.message.reply_text(MSG_HELP_ID_DESTINATION,
        disable_web_page_preview=True)
        return DESTINATION

    if update.message.text and update.message.text.startswith("-100"):
        context.user_data['source_id'] = update.message.text.strip()
        await update.message.reply_text(MSG_HELP_ID_DESTINATION,
        disable_web_page_preview=True)
        return DESTINATION

    await update.message.reply_text(
        "Это не пересланное сообщение из чата и не ID группы. Пожалуйста, перешлите сообщение или отправьте ID вида -100XXXXXXXXX."
    )
    return SOURCE



async def destination_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.forward_from_chat:
        destination_id = str(update.message.forward_from_chat.id)
    elif update.message.text and update.message.text.startswith("-100"):
        destination_id = update.message.text.strip()
    else:
        await update.message.reply_text(
            "Это не пересланное сообщение из чата и не ID группы. Пожалуйста, перешлите сообщение или отправьте ID вида -100XXXXXXXXX."
        )
        return DESTINATION

    source_id = context.user_data['source_id']
    user_id = str(update.effective_user.id)

    try:
        await db.add_subscription(source_id, destination_id, user_id)
        await update.message.reply_text(
            f"✅ Подписка добавлена!\n\n"
            f"Источник: {source_id}\n"
            f"Назначение: {destination_id}"
        )
    except Exception as e:
        logger.error(f"Ошибка при добавлении подписки: {e}")
        await update.message.reply_text("❌ Ошибка при добавлении подписки. Попробуйте позже.")

    context.user_data.clear()
    return ConversationHandler.END



async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in whitelist_ids:
        return

    user_id = str(update.effective_user.id)
    try:
        subscriptions = await db.get_subscriptions(user_id=user_id)
        if not subscriptions:
            await update.message.reply_text("У вас нет активных подписок.")
            return

        response = "📋 Ваши подписки:\n\n"
        for sub in subscriptions:
            response += (
                f"ID: {sub['id']}\n"
                f"Источник: {sub['source_id']}\n"
                f"Назначение: {sub['destination_id']}\n"
                f"Дата создания: {sub['created_date']}\n\n"
            )
        await update.message.reply_text(response)
    except Exception as e:
        logger.error(f"Ошибка при получении подписок: {e}")
        await update.message.reply_text("❌ Ошибка при получении подписок.")


async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in whitelist_ids:
        return

    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите ID подписки для удаления.\nПример: /remove 5")
        return

    try:
        sub_id = int(context.args[0])
        user_id = str(update.effective_user.id)

        deleted = await db.delete_subscription_by_user(sub_id, user_id)

        if deleted:
            await update.message.reply_text(f"✅ Подписка {sub_id} удалена.")
        else:
            await update.message.reply_text(
                f"❌ Подписка {sub_id} не найдена или вы не являетесь ее владельцем."
            )
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Неверный формат команды. Используйте: /remove <ID>")
    except Exception as e:
        logger.error(f"Ошибка при удалении подписки: {e}")
        await update.message.reply_text("❌ Ошибка при удалении подписки.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Действие отменено.")
    context.user_data.clear()
    return ConversationHandler.END


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    source = update.effective_chat

    logger.info(f"Received message from chat: {source.id} (type: {source.type})")

    chat_id = str(message.chat.id)

    try:
        subscriptions = await db.get_subscriptions_by_source(chat_id)

        if not subscriptions:
            return

        logger.info(f"Получено сообщение из {chat_id}: {message}")

        for subscription in subscriptions:
            try:
                await message.forward(
                    chat_id=subscription["destination_id"],
                    message_thread_id=message.message_thread_id
                )
                logger.debug(f"Сообщение переслано в {subscription['destination_id']}")
            except Exception as e:
                logger.error(f"Ошибка при пересылке в {subscription['destination_id']}: {e}")
                try:
                    await context.bot.copy_message(
                        chat_id=subscription["destination_id"],
                        from_chat_id=message.chat_id,
                        message_id=message.message_id,
                        message_thread_id=message.message_thread_id
                    )
                    logger.debug(f"Сообщение скопировано в {subscription['destination_id']}")
                except Exception as copy_error:
                    logger.error(f"Ошибка при копировании в {subscription['destination_id']}: {copy_error}")

    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")


logger.info("Bot started")
config_dict = get_config()
bot_token = config_dict['bot_token']
whitelist_ids = config_dict['whitelist_ids']

conv_handler = ConversationHandler(
    entry_points=[CommandHandler('add', add_command)],
    states={
        SOURCE: [
            MessageHandler(
                filters.FORWARDED | filters.TEXT,
                source_step
            )
        ],
        DESTINATION: [
            MessageHandler(
                filters.FORWARDED | filters.TEXT,
                destination_step
            )
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

app = ApplicationBuilder().token(bot_token).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("list", list_command))
app.add_handler(CommandHandler("remove", remove_command))
app.add_handler(conv_handler)

app.add_handler(MessageHandler(
    filters.ChatType.CHANNEL | filters.ChatType.GROUP | filters.ChatType.SUPERGROUP
    & ~filters.COMMAND
    & ~filters.StatusUpdate.ALL,
    handle_message
))


app.run_polling(
    drop_pending_updates=True,
    allowed_updates=["message", "channel_post", "edited_message"]
)