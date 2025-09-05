import aiosqlite
import asyncio
from datetime import datetime

DB_PATH = "data/subscriptions.db"


async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
                         CREATE TABLE IF NOT EXISTS subscriptions
                         (
                             id              INTEGER PRIMARY KEY AUTOINCREMENT,
                             source_id       TEXT NOT NULL,
                             destination_id  TEXT NOT NULL,
                             user_id_created TEXT NOT NULL,
                             created_date    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                         )
                         """)
        await db.commit()


async def add_subscription(source_id: str, destination_id: str, user_id_created: str):
    """Добавление новой подписки"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
                         INSERT INTO subscriptions (source_id, destination_id, user_id_created)
                         VALUES (?, ?, ?)
                         """, (source_id, destination_id, user_id_created))
        await db.commit()


async def get_subscriptions_by_source(source_id: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT * FROM subscriptions WHERE source_id = ?",
            (source_id,)
        )

        # Получаем данные с именами колонок
        columns = [col[0] for col in cursor.description]
        results = await cursor.fetchall()
        return [dict(zip(columns, row)) for row in results]


async def get_subscriptions(user_id: str = None):
    """Получение подписок с возможностью фильтрации по пользователю"""
    async with aiosqlite.connect(DB_PATH) as db:
        if user_id:
            cursor = await db.execute(
                "SELECT * FROM subscriptions WHERE user_id_created = ?",
                (user_id,)
            )
        else:
            cursor = await db.execute("SELECT * FROM subscriptions")

        # Получаем данные с именами колонок
        columns = [col[0] for col in cursor.description]
        results = await cursor.fetchall()
        return [dict(zip(columns, row)) for row in results]


async def delete_subscription_by_user(sub_id: int, user_id: str) -> bool:
    """Удаление подписки с проверкой владельца"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
                                  DELETE
                                  FROM subscriptions
                                  WHERE id = ?
                                    AND user_id_created = ?
                                  """, (sub_id, user_id))
        await db.commit()
        return cursor.rowcount > 0


# Пример использования
async def main():
    await init_db()

    # # Тестовые данные
    # await add_subscription("source_123", "dest_456", "user_789")
    # print("Подписка добавлена")
    #
    # subs = await get_subscriptions()
    # print("Все подписки:", subs)
    #
    # if subs:
    #     deleted = await delete_subscription_by_user(subs[0]['id'], "user_789")
    #     print(f"Удаление подписки: {'Успешно' if deleted else 'Не удалось'}")


if __name__ == "__main__":
    asyncio.run(main())