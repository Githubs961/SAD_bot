import json
import os
from functools import lru_cache
import aiohttp
import requests
from dotenv import load_dotenv
import asyncio
from datetime import datetime, timedelta
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
                              GetBandwidthStatsResponseDto)



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

TTL_SECONDS = 600 # 10 минут — хранится кэш в сек


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

        # так же получаем информацию об устройствах пользователя
        devices: HwidUserDeviceDto = await remnawave.hwid.get_hwid_user(str(user['uuid']))
        # и добавляем устройства к данным о пользователе
        user['devices'] = devices.devices

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

        # Рассчитываем дату истечения
        expire_at = datetime.utcnow() + timedelta(days=expire_days)


        await remnawave.users.create_user(CreateUserRequestDto(
            username=f'{username}_{telegram_id}', # нужно уникольное имя комбинируем ник и tg_id
            active_internal_squads=["6002d566-a23d-40d4-82c7-624c2a7777b0","ecb4eace-49a3-4bdc-b9a7-190500b40e71"],#СКВАДЫ
            expire_at=expire_at,  # обязательное поле
            telegram_id=telegram_id,
            email=email,
            description='Пробный период 3 дня',
            traffic_limit_bytes=traffic_limit_bytes * 1024 * 1024 * 1024 if traffic_limit_bytes > 0 else 0,  # в байтах
            hwid_device_limit=hwid_limit,
            status="ACTIVE",
            traffic_limit_strategy="MONTH"))

        # 🔥 получаем пользователя
        user : TelegramUserResponseDto = await remnawave.users.get_users_by_telegram_id(telegram_id)

        if not user:
            return None

        user_data = user.root[0].model_dump()

        return {
            "uuid": str(user_data["uuid"]),
            "username": user_data["username"],
            "subscription_url": user_data["subscription_url"]
        }



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
# def format_expire_date(expire_str: datetime) -> str:
#     if not expire_str:
#         return "—"
#     """Красиво форматирует дату окончания подписки"""
#     try:
#         # Форматируем в удобный вид
#         return expire_str.strftime("%d.%m.%Y %H:%M")
#         # Примеры вывода:
#         # 07 апреля 2026, 06:41
#         # 15 мая 2026, 23:59
#     except:
#         return "—"
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo  # Python 3.9+, или используйте pytz


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
async def get_node_user_stats():
    uuid = 'a2fcefb8-ee25-484a-8fb9-89ef8f1145ec'  # id ноды яндекс
    url = f"https://panelsubarikvpn.mooo.com/api/bandwidth-stats/nodes/{uuid}/users"

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
        async with session.get(url, params=params, headers=headers, cookies={secret_name: secret_value}) as resp:
            data = await resp.json()
            return data["response"]["topUsers"]








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



    # devices: HwidUserDeviceDto = await remnawave.hwid.get_hwid_user('7c2738ca-dce1-44b3-8bcb-6a2b000ee217')

    # print(devices.devices)
    # print(len(devices.devices))



    data = await get_user('758504107')
    print("DATA:", data['uuid'])

     # Сохранение users.json с панели remnawave_client
    with open('../cache/users_1.txt', 'w', encoding='utf-8') as file:
     file.writelines(data)


if __name__ == "__main__":
 asyncio.run(main())
