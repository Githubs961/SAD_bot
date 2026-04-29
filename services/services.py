import asyncio
from datetime import datetime, timedelta
from database import get_db_connection, db_lock
from lexicon.lexicon import TRAFFIC_SEC
from remnawave_api.api_remnavawe import get_node_user_stats, remnawave
from database import get_db_connection
from remnawave.models import UpdateUserRequestDto




# Обновление статистики трафика
async def update_traffic():
    users_stats = await get_node_user_stats()


    to_disable = set()
    now = datetime.utcnow()

    async with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()

        # ✅ 1. создаём map один раз
        cursor.execute("SELECT user_id, username FROM users")
        users_map = {row["username"]: row["user_id"] for row in cursor.fetchall()}

        for stat in users_stats:
            username = stat["username"]
            total = stat["total"]

            user_id = users_map.get(username)
            if not user_id:
                continue

            # ✅ 2. берём трафик (только активные)
            cursor.execute("""
                SELECT * FROM user_traffic 
                WHERE user_id = ? AND is_active = 1
            """, (user_id,))

            traffic = cursor.fetchone()
            if not traffic:
                continue

            # -----------------------------
            # 🔁 3. ПРОВЕРКА ПЕРИОДА
            # -----------------------------
            period_end = datetime.fromisoformat(traffic["period_end"])

            if now >= period_end:
                print(f"🔄 Новый период для {user_id}")

                new_end = now + timedelta(days=30)

                cursor.execute("""
                            UPDATE user_traffic
                            SET used_bytes = 0,
                                period_start = ?,
                                period_end = ?,
                                last_total_bytes = ?,  -- 🔥 фиксируем текущее значение API
                                updated_at = ?,
                                is_active = 1
                            WHERE user_id = ?
                        """, (
                    now.isoformat(),
                    new_end.isoformat(),
                    total,  # ❗ ВАЖНО
                    now.isoformat(),
                    user_id
                ))

                continue  # 👉 идём к следующему пользователю

            # СЧИТАЕМ ДЕЛЬТУ
            last_total = traffic["last_total_bytes"]

            delta = total - last_total
            if delta < 0:
                delta = 0

            new_used = traffic["used_bytes"] + delta

            # ОБНОВЛЯЕМ ТРАФИК
            cursor.execute('''
                UPDATE user_traffic
                SET used_bytes = ?,
                    last_total_bytes = ?,
                    updated_at = ?
                WHERE user_id = ?
            ''', (
                new_used,
                total,
                datetime.utcnow().isoformat(),
                user_id
            ))

            # 🚨 ПРОВЕРКА ЛИМИТА
            if new_used >= traffic["traffic_limit"]:

                print(f"🚫 Пользователь {user_id} превысил лимит")
                to_disable.add(user_id)

                cursor.execute("""
                    UPDATE user_traffic
                    SET is_active = 0
                    WHERE user_id = ?
                """, (user_id,))

        conn.commit()
        conn.close()

    # ✅ вне lock
    for user_id in to_disable:
        await disable_user_squad(user_id)



# Автопроверка трафика в фоне
async def traffic_worker():
    while True:
        try:
            await update_traffic()
            print("📊 Трафик обновлён")
        except Exception as e:
            print(f"❌ Ошибка update_traffic: {e}")

        await asyncio.sleep(TRAFFIC_SEC) # (в сек)



# Сброс трафика(при оплате)
async def reset_traffic(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    now = datetime.utcnow()
    end = now + timedelta(days=30)

    # 🔥 ВАЖНО: берем текущий total из БД
    cursor.execute("""
        SELECT last_total_bytes FROM user_traffic WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()

    last_total = row["last_total_bytes"] if row else 0

    cursor.execute("""
        UPDATE user_traffic
        SET used_bytes = 0,
            last_total_bytes = ?,
            period_start = ?,
            period_end = ?,
            updated_at = ?,
            is_active = 1
        WHERE user_id = ?
    """, (
        last_total,  # сохраняем текущее значение
        now.isoformat(),
        end.isoformat(),
        now.isoformat(),
        user_id
    ))

    conn.commit()
    conn.close()




# Лимит трафика для ноды при создании пользователя заносим в БД
async def init_traffic(user_id: int):
    traffic_limit_bytes = 50 * 1024 ** 3 # 50 ГБ

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM user_traffic WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        conn.close()
        return

    now = datetime.utcnow()
    end = now + timedelta(days=30)

    cursor.execute('''
        INSERT INTO user_traffic (
            user_id, node_id, used_bytes,
            traffic_limit, period_start, period_end,
            last_total_bytes, updated_at
        )
        VALUES (?, ?, 0, ?, ?, ?, 0, ?)
    ''', (
        user_id,
        "YANDEX_NODE",
        traffic_limit_bytes,
        now.isoformat(),
        end.isoformat(),
        now.isoformat()
    ))

    conn.commit()
    conn.close()





# Отключнние сквады Яндекс при превышении лимита трафика
async def disable_user_squad(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    # 👉 проверяем статус
    cursor.execute("""
        SELECT uuid, is_active 
        FROM user_traffic 
        JOIN users USING(user_id)
        WHERE user_id = ?
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return

    uuid = row["uuid"]

    user = await remnawave.users.get_user_by_uuid(uuid)

    squads = [str(s.uuid) for s in user.active_internal_squads]

    YANDEX_NODE_ID = "ecb4eace-49a3-4bdc-b9a7-190500b40e71"

    # ❗ если уже нет ноды — НЕ трогаем
    if YANDEX_NODE_ID not in squads:
        return

    new_squads = [s for s in squads if s != YANDEX_NODE_ID]

    await remnawave.users.update_user(UpdateUserRequestDto(
        uuid=uuid,
        active_internal_squads=new_squads
    ))

    # 👉 фиксируем в БД
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE user_traffic
        SET is_active = 0
        WHERE user_id = ?
    """, (user_id,))

    conn.commit()
    conn.close()

    print(f"🚫 Пользователь {user_id} отключен от Yandex ноды")




# Включение сквады Яндекс при обновлении подписки(если был превышен трафик и она отключалась)
async def enable_user_squad(user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT uuid FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return

    uuid = row["uuid"]

    user = await remnawave.users.get_user_by_uuid(uuid)
    squads = [str(s.uuid) for s in user.active_internal_squads]

    YANDEX_NODE_ID = "ecb4eace-49a3-4bdc-b9a7-190500b40e71"

    if YANDEX_NODE_ID in squads:
        return

    new_squads = squads + [YANDEX_NODE_ID]

    await remnawave.users.update_user(UpdateUserRequestDto(
        uuid=uuid,
        active_internal_squads=new_squads
    ))

    # ✅ ОТКРЫВАЕМ НОВОЕ СОЕДИНЕНИЕ
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE user_traffic
        SET is_active = 1
        WHERE user_id = ?
    """, (user_id,))

    conn.commit()
    conn.close()

    print(f"✅ Пользователь {user_id} снова подключен к Yandex ноде")