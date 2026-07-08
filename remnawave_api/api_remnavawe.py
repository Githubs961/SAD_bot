import json
import os
from functools import lru_cache
import aiohttp
import requests
from dotenv import load_dotenv
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from remnawave import RemnawaveSDK  # Updated import for new package
from remnawave.models import (UsersResponseDto,
                              UserResponseDto,
                              CreateUserRequestDto,
                              GetAllConfigProfilesResponseDto,
                              CreateInternalSquadRequestDto,
                              TelegramUserResponseDto,
                              HwidUserDeviceDto,
                              UpdateUserRequestDto,
                              GetBandwidthStatsResponseDto, HWIDDeleteRequest)

from lexicon.lexicon import SQUADS, LTE_NODE_UUID

load_dotenv()  # вызов переменных окружения, файл ".env"

# URL to your panel (ex. https://vpn.com or http://127.0.0.1:3000)
base_url: str = os.getenv("PANEL_URL")
# Bearer Token from panel (section: API Tokens)
token: str = os.getenv("REMNAWAVE_TOKEN")
# secret_name и secret_value искать в файле nginx на сервере opt/remnawave
secret_name = os.getenv('SECRET_NAME')
secret_value = os.getenv('SECRET_VALUE')

# Initialize the SDK
remnawave = RemnawaveSDK(base_url=base_url, token=token, cookies={secret_name: secret_value})



# Глобальный кэш
user_cache: Dict[str, Dict] = {}
cache_time: Dict[str, float] = {}
locks: Dict[str, asyncio.Lock] = {}  # защита от одновременной записи

TTL_SECONDS = 300 # 5 минут — хранится кэш в сек


# Функция для очистки кэша (можно вызывать после создания/продления подписки)
async def invalidate_user_cache(telegram_id: str):
    lock = locks.setdefault(telegram_id,asyncio.Lock())
    async with lock:
        user_cache.pop(telegram_id, None)
        cache_time.pop(telegram_id, None)



#Найти пользователя по telegram_id
async def get_user(telegram_id: str) -> Optional[dict]:

    # 1. Проверяем кэш под блокировкой
    lock = locks.setdefault(telegram_id, asyncio.Lock())
    async with lock:
        now = datetime.utcnow().timestamp()
        if (telegram_id in user_cache and
                now - cache_time.get(telegram_id, 0) < TTL_SECONDS):
            print(f"[DEBUG] Возвращаю из кэша для {telegram_id}")
            return user_cache[telegram_id]
    # 2. Если в кэше нет или устарел — идём в Remnawave
    print(f"[DEBUG] Кэш устарел или пуст, иду в API для {telegram_id}")
    try:
        response: TelegramUserResponseDto =await remnawave.users.get_users_by_telegram_id(telegram_id)
        if not response:
            print(f"[DEBUG] Пользователь {telegram_id} не найден в API")
            return None

        # Преобразуем в чистый dict
        user = response.root[0].model_dump()

        # # так же получаем информацию об устройствах пользователя
        # devices: HwidUserDeviceDto = await remnawave.hwid.get_hwid_user(str(user['uuid']))
        # # и добавляем устройства к данным о пользователе
        # user['devices'] = devices.devices
        devices = await get_user_devices_raw(str(user['uuid']))
        user['devices'] = devices

        # Сохраняем в кэш
        async with lock:
            user_cache[telegram_id] = user
            cache_time[telegram_id] = datetime.utcnow().timestamp()

        print(f"[DEBUG] Пользователь {telegram_id} сохранён в кэш")
        return  user # возвращаем словарь - информация о пользователе

    except asyncio.TimeoutError:
        print(f"[DEBUG] Таймаут API для {telegram_id}")
        return None
    except Exception as e:
        print(f"Ошибка при получении пользователя {telegram_id}: {e}")
        return None





# Создание пользователя и выдача пробного периода
async def create_new_user(username: str,
                      expire_days: int = 3,
                      traffic_limit_bytes: int = 0,
                      telegram_id: Optional[str] = None,
                      email: Optional[str] = None,
                      active_internal_squads: list = None,
                      note: str = "",
                      hwid_limit: int = 3):
    # Сначала пытаемся найти пользователя по telegram_id
    try:
        existing = await remnawave.users.get_users_by_telegram_id(telegram_id)
        if existing and existing.root:
            user_data = existing.root[0].model_dump()
            print(f"✅ Пользователь уже существует: {user_data['username']}")
            return {
                "uuid": str(user_data["uuid"]),
                "username": user_data["username"],
                "subscription_url": user_data.get("subscription_url")
            }
    except Exception as e:
        print(f"Пользователь не найден, создаём нового: {e}")

    # Если не нашли — создаём
    try:
        expire_at = datetime.utcnow() + timedelta(days=expire_days)

        await remnawave.users.create_user(CreateUserRequestDto(
            username=f"{username or 'user'}_{telegram_id}",  # уникальное имя
            telegram_id=telegram_id,
            expire_at=expire_at,
            active_internal_squads=SQUADS,
            description="Пробный период 3 дня",
            traffic_limit_bytes=traffic_limit_bytes * 1024 * 1024 * 1024,
            hwid_device_limit=hwid_limit,
            status="ACTIVE",
            traffic_limit_strategy="MONTH"
        ))

        # После создания снова получаем пользователя
        user = await remnawave.users.get_users_by_telegram_id(telegram_id)
        if user and user.root:
            user_data = user.root[0].model_dump()
            return {
                "uuid": str(user_data["uuid"]),
                "username": user_data["username"],
                "subscription_url": user_data.get("subscription_url")
            }
    except Exception as e:
        print(f"Ошибка создания пользователя: {e}")
        return None

    return None

        # # Рассчитываем дату истечения
        # expire_at = datetime.utcnow() + timedelta(days=expire_days)
        #
        # await remnawave.users.create_user(CreateUserRequestDto(
        #     username=f'{username}_{telegram_id}', # нужно уникольное имя комбинируем ник и tg_id
        #     active_internal_squads=SQUADS, #СКВАДЫ Пользователя
        #     expire_at=expire_at,  # обязательное поле
        #     telegram_id=telegram_id,
        #     email=email,
        #     description='Пробный период 3 дня',
        #     traffic_limit_bytes=traffic_limit_bytes * 1024 * 1024 * 1024 if traffic_limit_bytes > 0 else 0,  # в байтах
        #     hwid_device_limit=hwid_limit,
        #     status="ACTIVE",
        #     traffic_limit_strategy="MONTH"))
        #
        # # 🔥 получаем пользователя
        # user : TelegramUserResponseDto = await remnawave.users.get_users_by_telegram_id(telegram_id)
        #
        # if not user:
        #     return None
        #
        # user_data = user.root[0].model_dump()
        #
        # return {
        #     "uuid": str(user_data["uuid"]),
        #     "username": user_data["username"],
        #     "subscription_url": user_data["subscription_url"]
        # }



# После оплаты прибавляем пользователю длительность подписки (дни)
async def add_days(telegram_id: str, days:int):
    try:
        response: TelegramUserResponseDto = await remnawave.users.get_users_by_telegram_id(telegram_id)
        if not response:
            return False
        # Преобразуем в чистый dict
        user = response.root[0].model_dump()
        # время действия подписки
        expire_at = user['expire_at']

        if expire_at and user['status'] == 'ACTIVE':
            # подписка ещё активная и статус ACTIVE
            base_date = expire_at
        else:
            base_date = datetime.utcnow()

        # Новая дата окончания подписки
        new_expires = base_date + timedelta(days=days)

        await remnawave.users.update_user(UpdateUserRequestDto(
                                            uuid=user["uuid"],
                                            expire_at=new_expires.isoformat()
        ))
        #Очистка кэша
        await invalidate_user_cache(str(telegram_id))

        return True
    except Exception as e:
        print(f"Ошибка при получении пользователя {telegram_id}: {e}")
        return None





# Преобразование даты окончания подписки в норм вид
def format_expire_date(expire_str: datetime, local_offset: int = 3) -> str:
    """
    Красиво форматирует дату окончания подписки с конвертацией UTC → локальное время

    Args:
        expire_str: дата из API (обычно в UTC)
        local_offset: смещение в часах относительно UTC (для Мск = 3)
    """
    if not expire_str:
        return "∞ (бессрочно)"

    try:
        # Если пришла строка, а не datetime
        if isinstance(expire_str, str):
            # Убираем 'Z' и конвертируем
            expire_str = expire_str.replace('Z', '+00:00')
            dt = datetime.fromisoformat(expire_str)
        else:
            dt = expire_str

        # Если время наивное (без timezone), добавляем UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Конвертируем в локальное время (UTC + offset)
        local_dt = dt.astimezone(timezone(timedelta(hours=local_offset)))

        # Форматируем
        return local_dt.strftime("%d.%m.%Y %H:%M")

    except Exception as e:
        print(f"Ошибка форматирования даты: {e}")
        return "—"


# Получение трафика на ноде
async def get_node_user_stats(node_uuid):
    #uuid = LTE_NODE_UUID   # id ноды для LTE
    url = f"https://newpan.myproject123.site/api/bandwidth-stats/nodes/{node_uuid}/users"

    today = datetime.utcnow().date()
    start = today - timedelta(days=1)

    params = {
        "start": start.isoformat(),
        "end": today.isoformat(),
        "topUsersLimit": 10000
    }

    headers = {
        "Authorization": f"Bearer {token}"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params,
                                    headers=headers,
                                    cookies={secret_name: secret_value}) as resp:
            data = await resp.json()
            return data["response"]["topUsers"]




# Получение устройств пользователя
async def get_user_devices_raw(user_uuid: str) -> list:
    """Получает устройства через прямой запрос к API"""
    url = f"{base_url}/api/hwid/devices/{user_uuid}"
    headers = {"Authorization": f"Bearer {token}"}
    cookies = {secret_name: secret_value}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, cookies=cookies, timeout=10) as resp:

                if resp.status != 200:
                    print(f"[WARN] Ошибка: {resp.status}")
                    return []

                data = await resp.json()
                #print(f"[DEBUG] Полный ответ API: {json.dumps(data, indent=2, default=str)}")

                # Здесь вы увидите реальную структуру ответа
                # и сможете понять, где лежат устройства

                # Попробуем разные варианты извлечения
                if isinstance(data, dict):
                    # Вариант 1: прямой ключ "devices"
                    if "devices" in data:
                        devices = data["devices"]
                        return devices

                    # Вариант 2: ключ "response"
                    if "response" in data and isinstance(data["response"], dict):
                        if "devices" in data["response"]:
                            devices = data["response"]["devices"]
                            return devices
                        if isinstance(data["response"], list):
                            return data["response"]

                    # Вариант 3: данные сами являются списком
                    if isinstance(data, list):
                        print(f"[DEBUG] Ответ — список устройств: {len(data)}")
                        return data

                    # Вариант 4: данные лежат в другом ключе
                    print(f"[DEBUG] Ключи ответа: {list(data.keys())}")

                # Если ничего не нашли
                print("[WARN] Не удалось найти устройства в ответе")
                return []

    except Exception as e:
        print(f"[ERROR] get_user_devices_raw: {e}")
        return []



# Удаление устройства пользователя
async def delete_user_device(telegram_id: str, user_uuid: str, hwid: str) -> bool:
    try:
        await remnawave.hwid.delete_hwid_to_user(
            HWIDDeleteRequest(
                user_uuid=user_uuid,
                hwid=hwid
            )
        )

        return True

    except Exception as e:
        print(f"delete_user_device error: {e}")
        return False







#для тестирования
async def main():
 # Fetch all users

    await add_days('758504107',10)

    response: UsersResponseDto = await remnawave.users.get_users_by_telegram_id('758504107')


    user = response.root[0].model_dump()
    print(user['uuid'])


    uuid = 'a2fcefb8-ee25-484a-8fb9-89ef8f1145ec' # id ноды яндекс

    # traffic: GetBandwidthStatsResponseDto = remnawave.bandwidthstats.get_stats_nodes_usage()
    # resp_band = await remnawave.nodes.get_all_nodes()
    # print(resp_band)



    devices: HwidUserDeviceDto = await remnawave.hwid.get_hwid_user('104b38db-77b8-4991-862b-86ecd31ab3ab')
    devices2: HwidUserDeviceDto = await remnawave.hwid.delete_hwid_to_user(HWIDDeleteRequest(
                user_uuid=user["uuid"],
                hwid='awyfqkhvbx6ls3r3'
            ))
    print(devices.devices)
    print(len(devices.devices))




    data = await get_user('758504107')
    print("DATA:", data['uuid'])

     # Сохранение users.json с панели remnawave_client
    with open('../cache/users_1.txt', 'w', encoding='utf-8') as file:
     file.writelines(data)


if __name__ == "__main__":
 asyncio.run(main())
