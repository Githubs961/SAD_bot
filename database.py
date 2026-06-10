import sqlite3
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from aiogram import Bot

from lexicon.lexicon import PAY_STARS


DB_PATH = Path("bot_database.db")

# 🔒 Глобальный lock для записи
db_lock = asyncio.Lock()

# Создаём подключение
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # чтобы возвращались словари
    return conn


# Инициализация базы данных
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 🔥 включаем WAL режим (уменьшает блокировки)
    cursor.execute("PRAGMA journal_mode=WAL;")

    # Таблица платежей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL, 
            status TEXT DEFAULT 'PENDING', 
            user_id INTEGER NOT NULL,
            transactionId TEXT UNIQUE NOT NULL,
            plan_key TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            processed_at TEXT,
            redirect TEXT
        )
    ''')
    # Статусы   -- PENDING / CONFIRMED / CANCELED


    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_traffic (
            user_id INTEGER PRIMARY KEY,
            node_id TEXT NOT NULL,              -- нода (Яндекс)
            used_bytes INTEGER DEFAULT 0,       -- сколько использовано
            traffic_limit INTEGER NOT NULL,     -- лимит (например 50GB)
            period_start TEXT NOT NULL,         -- начало периода
            period_end TEXT NOT NULL,           -- конец (через 30 дней)
            last_total_bytes INTEGER DEFAULT 0, -- прошлое значение из API
            updated_at TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            uuid TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            rewarded INTEGER DEFAULT 0
            )
        ''')


    conn.commit()
    conn.close()
    print("✅ База данных успешно инициализирована")


# Сохранение пользователя в БД
async def save_user(user_id: int, username: str, uuid: str):
    async with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO users (user_id, username, uuid)
            VALUES (?, ?, ?)
        """, (user_id, username, uuid))

        conn.commit()
        conn.close()


# Сохранение платежа STARS
async def save_payment(user_id: int, provider: str, status: str, transactionId: str, plan_key: str, amount: int, currency:str, redirect: str = None):
    async with db_lock:  # 🔒 защита от параллельной записи
        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO payments 
                (user_id, provider, status, transactionId, plan_key, amount, currency, redirect, processed_at )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, provider, status, transactionId, plan_key, amount,currency, redirect, datetime.utcnow().isoformat()))

            conn.commit()
            print(f"✅ Платёж {transactionId} сохранён")
            return True
        except sqlite3.IntegrityError:
            print(f"Платёж {transactionId} уже был сохранён ранее")
            return False
        except Exception as e:
            print(f"❌ Ошибка сохранения платежа: {e}")
        finally:
            conn.close()



# проверка существующего плвтежа Platega
def get_active_payment(user_id: int, plan_key: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM payments
        WHERE user_id = ?
        AND plan_key = ?
        AND status = 'PENDING'
        AND created_at > datetime('now', '-30 minutes')
        ORDER BY id DESC
        LIMIT 1
    """, (user_id, plan_key))

    row = cursor.fetchone()
    conn.close()
    return row




# Проверяем и Обнавляем БД после платежа Platega
def update_db(status, transaction_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # 👉 берём старый статус
    cursor.execute("""
        SELECT status, user_id, plan_key
        FROM payments
        WHERE transactionId = ?
    """, (transaction_id,))

    row = cursor.fetchone()

    if not row:
        conn.close()
        return None

    old_status = row["status"]

    # 👉 обновляем только если статус изменился
    if old_status != status:
        cursor.execute("""
            UPDATE payments
            SET status = ?, processed_at = ?
            WHERE transactionId = ?
        """, (
            status,
            datetime.utcnow().isoformat(),
            transaction_id
        ))
        conn.commit()

    conn.close()

    return {
        "user_id": row["user_id"],
        "plan_key": row["plan_key"],
        "old_status": old_status
    }




# Платеж не оплачен пометка EXPIRED в БД
async def expire_old_payments():
    while True:
        now = datetime.utcnow()
        next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)

        if next_run <= now:
            next_run += timedelta(days=1)

        sleep_time = (next_run - now).total_seconds()
        await asyncio.sleep(sleep_time)

        # 🔥 твоя очистка
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
                UPDATE payments
                SET status = 'EXPIRED',
                    processed_at = ?
                WHERE status = 'PENDING'
                AND created_at < datetime('now', '-30 minutes')
            """, (datetime.utcnow().isoformat(),))

        conn.commit()
        conn.close()

        print("🧹 Очистка выполнена")



# Трафик пользователя, для личного кабинета
def get_user_traffic(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT used_bytes, traffic_limit, period_end
        FROM user_traffic
        WHERE user_id = ?
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()

    return row


#Реферальная система - Сохранение и проверки
async def save_referral(referrer_id: int, referred_id: int) -> bool:
    """Сохраняет реферала. Возвращает True, если запись создана."""
    if referrer_id == referred_id:
        return False

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Проверка, что пользователь ещё не был приглашён
        cursor.execute("SELECT 1 FROM referrals WHERE referred_id = ?", (referred_id,))
        if cursor.fetchone():
            return False

        cursor.execute("""
            INSERT INTO referrals (referrer_id, referred_id, rewarded)
            VALUES (?, ?, 0)
        """, (referrer_id, referred_id))

        conn.commit()
        return True

    except Exception as e:
        print(f"Referral save error: {e}")
        return False
    finally:
        conn.close()


# ====================== РЕФЕРАЛЬНАЯ СИСТЕМА ======================

async def process_referral_reward(referred_id: int, bot: Bot = None) -> bool:
    """
    Начисляет +15 дней рефереру после первой оплаты referred_id.
    Возвращает True, если награда выдана.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT referrer_id 
            FROM referrals 
            WHERE referred_id = ? AND rewarded = 0
        """, (referred_id,))

        row = cursor.fetchone()
        if not row:
            return False  # уже награждён или реферала нет

        referrer_id = row[0]

        # === Начисляем +15 дней рефереру через API ===
        from remnawave_api.api_remnavawe import add_days  # импортируем здесь, чтобы избежать циклического импорта

        success = await add_days(telegram_id=str(referrer_id), days=15)

        if success:
            # Помечаем как rewarded
            cursor.execute("""
                UPDATE referrals 
                SET rewarded = 1 
                WHERE referred_id = ?
            """, (referred_id,))
            conn.commit()

            # Уведомляем реферера
            if bot:
                try:
                    await bot.send_message(
                        chat_id=referrer_id,
                        text="🎁 <b>Реферальная награда!</b>\n\n"
                             "Ваш друг оплатил подписку.\n"
                             "Вам начислено +15 дней к подписке!",
                        parse_mode="HTML"
                    )
                except:
                    pass  # пользователь мог заблокировать бота

            print(f"✅ Реферальная награда выдана: {referrer_id} (+15 дней)")
            return True

        else:
            print(f"❌ Не удалось начислить реферальные дни для {referrer_id}")
            return False

    except Exception as e:
        print(f"❌ process_referral_reward error: {e}")
        return False
    finally:
        conn.close()



#Статистика рефералов (для Личного кабинета)
async def get_referral_stats(user_id: int) -> dict:
    """
    Возвращает статистику рефералов пользователя.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Сколько всего пригласил
        cursor.execute("""
            SELECT COUNT(*) FROM referrals WHERE referrer_id = ?
        """, (user_id,))
        total_refs = cursor.fetchone()[0]

        # Сколько уже принесли награду
        cursor.execute("""
            SELECT COUNT(*) FROM referrals 
            WHERE referrer_id = ? AND rewarded = 1
        """, (user_id,))
        rewarded = cursor.fetchone()[0]

        return {
            "total": total_refs,
            "rewarded": rewarded
        }

    except Exception as e:
        print(f"get_referral_stats error: {e}")
        return {"total": 0, "rewarded": 0}
    finally:
        conn.close()