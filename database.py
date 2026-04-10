import sqlite3
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from lexicon.lexicon import PAY_STARS

DB_PATH = Path("bot_database.db")


# Создаём подключение
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # чтобы возвращались словари
    return conn


# Инициализация базы данных
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Таблица платежей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            telegram_payment_charge_id TEXT UNIQUE NOT NULL,
            plan_key TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            status TEXT DEFAULT 'completed',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            processed_at TEXT
        )
    ''')

    # Таблица подписок пользователей (чтобы знать текущую подписку)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_subscriptions (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            plan_key TEXT,
            expire_at TEXT,
            telegram_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT
        )
    ''')

    conn.commit()
    conn.close()
    print("✅ База данных успешно инициализирована")


# Сохранение платежа
async def save_payment(user_id: int, charge_id: str, plan_key: str, amount: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO payments 
            (user_id, telegram_payment_charge_id, plan_key, amount, currency, processed_at)
            VALUES (?, ?, ?, ?, 'XTR', ?)
        ''', (user_id, charge_id, plan_key, amount, datetime.utcnow().isoformat()))

        conn.commit()
        print(f"✅ Платёж {charge_id} сохранён")
        return True
    except sqlite3.IntegrityError:
        print(f"Платёж {charge_id} уже был сохранён ранее")
        return False
    except Exception as e:
        print(f"❌ Ошибка сохранения платежа: {e}")
    finally:
        conn.close()


# Выдача/продление подписки
async def grant_subscription(user_id: int, plan_key: str, telegram_id: int = None, username: str = None):
    # Здесь можно добавить логику расчёта expire_at в зависимости от тарифа
    days = PAY_STARS.get(plan_key)

    expire_at = (datetime.utcnow() + timedelta(days=days)).isoformat()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO user_subscriptions 
            (user_id, username, plan_key, expire_at, telegram_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
                plan_key = excluded.plan_key,
                expire_at = excluded.expire_at,
                username = excluded.username,
                updated_at = excluded.updated_at
        ''', (user_id, username, plan_key, expire_at, telegram_id, datetime.utcnow().isoformat()))

        conn.commit()
        print(f"✅ Подписка для пользователя {user_id} активирована ({plan_key})")
        return True
    except Exception as e:
        print(f"❌ Ошибка выдачи подписки: {e}")
        return False
    finally:
        conn.close()
