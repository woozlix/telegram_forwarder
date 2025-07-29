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
import db  # Импорт нашего модуля для работы с БД

# Состояния для ConversationHandler
SOURCE, DESTINATION = range(2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in whitelist_ids:
        return
    await update.message.reply_text(
        f'Привет {update.effective_user.first_name}!\n\n'
        f'Доступные команды:\n'
        f'/start - информация о боте\n'
        f'/add - добавить пересылку сообщений\n'
        f'/list - показать ваши подписки\n'
        f'/remove - удалить подписку'
    )


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id not in whitelist_ids:
        return ConversationHandler.END

    await update.message.reply_text(
        "Перешлите сообщение из ИСТОЧНИКА (откуда пересылать):"
    )
    return SOURCE


async def source_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Проверяем, что сообщение действительно переслано из чата
    if not update.message.forward_from_chat:
        await update.message.reply_text(
            "Это не пересланное сообщение из чата. Пожалуйста, перешлите сообщение из группы/канала."
        )
        return SOURCE

    # Сохраняем ID источника
    context.user_data['source_id'] = str(update.message.forward_from_chat.id)

    await update.message.reply_text(
        "Теперь перешлите сообщение из НАЗНАЧЕНИЯ (куда пересылать):"
    )
    return DESTINATION


async def destination_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.forward_from_chat:
        await update.message.reply_text(
            "Это не пересланное сообщение из чата. Пожалуйста, перешлите сообщение из группы/канала."
        )
        return DESTINATION

    # Получаем сохраненные данные
    source_id = context.user_data['source_id']
    destination_id = str(update.message.forward_from_chat.id)
    user_id = str(update.effective_user.id)

    try:
        # Сохраняем подписку в БД
        await db.add_subscription(source_id, destination_id, user_id)
        await update.message.reply_text(
            f"✅ Подписка добавлена!\n"
            f"Источник: {source_id}\n"
            f"Назначение: {destination_id}"
        )
    except Exception as e:
        logger.error(f"Ошибка при добавлении подписки: {e}")
        await update.message.reply_text("❌ Ошибка при добавлении подписки. Попробуйте позже.")

    # Очищаем временные данные
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

    # Проверяем наличие аргумента (ID подписки)
    if not context.args:
        await update.message.reply_text("Пожалуйста, укажите ID подписки для удаления.\nПример: /remove 5")
        return

    try:
        sub_id = int(context.args[0])
        user_id = str(update.effective_user.id)

        # Удаляем подписку
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


async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик сообщений из каналов
    """
    channel_post = update.channel_post
    if not channel_post:
        return

    chat_id = str(channel_post.chat.id)

    try:
        subscriptions = await db.get_subscriptions(chat_id)

        if not subscriptions:
            return

        logger.info(f"Получен пост из канала {chat_id} для {len(subscriptions)} подписок")

        for subscription in subscriptions:
            try:
                await channel_post.forward(
                    chat_id=subscription["destination_id"],
                    message_thread_id=channel_post.message_thread_id
                )
                logger.debug(f"Пост переслан в {subscription['destination_id']}")
            except Exception as e:
                logger.error(f"Ошибка при пересылке поста в {subscription['destination_id']}: {e}")
                try:
                    await context.bot.copy_message(
                        chat_id=subscription["destination_id"],
                        from_chat_id=channel_post.chat_id,
                        message_id=channel_post.message_id,
                        message_thread_id=channel_post.message_thread_id
                    )
                    logger.debug(f"Пост скопирован в {subscription['destination_id']}")
                except Exception as copy_error:
                    logger.error(f"Ошибка при копировании поста: {copy_error}")

    except Exception as e:
        logger.error(f"Ошибка обработки поста из канала: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик входящих сообщений из чатов
    """
    message = update.effective_message
    source = update.effective_chat

    logger.info(f"Received message from chat: {source.id} (type: {source.type})")

    chat_id = str(message.chat.id)

    try:
        # Получаем все подписки для этого источника
        subscriptions = await db.get_subscriptions_by_source(chat_id)

        if not subscriptions:
            return

        logger.info(f"Получено сообщение из {chat_id}: {message}")

        # Для каждой подписки пересылаем сообщение
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
                    # Пытаемся скопировать сообщение, если пересылка не удалась
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


# Инициализация и запуск бота
logger.info("Bot started")
config_dict = get_config()
bot_token = config_dict['bot_token']
whitelist_ids = config_dict['whitelist_ids']

# Создаем обработчик диалогов
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('add', add_command)],
    states={
        SOURCE: [
            MessageHandler(
                filters.FORWARDED & filters.ChatType.PRIVATE,
                source_step
            )
        ],
        DESTINATION: [
            MessageHandler(
                filters.FORWARDED & filters.ChatType.PRIVATE,
                destination_step
            )
        ],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
)

app = ApplicationBuilder().token(bot_token).build()

# Регистрируем обработчики
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("list", list_command))
app.add_handler(CommandHandler("remove", remove_command))
app.add_handler(conv_handler)

# Обработчик сообщений из групп/каналов
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