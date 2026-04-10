import json
import os
from functools import lru_cache
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
                              GetUserHwidDevicesResponseDto, UpdateUserRequestDto)


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


# class UserCache:
#     def __init__(self, ttl_seconds: int = 60):
#         self.cache: Dict[str, Dict] = {}           # telegram_id -> user_dict
#         self.cache_time: Dict[str, float] = {}     # telegram_id -> время последнего обновления
#         self.ttl = ttl_seconds                     # время жизни кэша в секундах
#
#     def get(self, telegram_id: str) -> Optional[dict]:
#         now = datetime.utcnow().timestamp()
#         if (telegram_id in self.cache and
#             now - self.cache_time.get(telegram_id, 0) < self.ttl):
#             return self.cache[telegram_id]
#         return None
#
#     def set(self, telegram_id: str, user_data: dict):
#         self.cache[telegram_id] = user_data
#         self.cache_time[telegram_id] = datetime.utcnow().timestamp()
#
#     def clear(self):
#         self.cache.clear()
#         self.cache_time.clear()
#
#
# # Глобальный кэш (можно сделать экземпляром класса)
# user_cache = UserCache(ttl_seconds=120)   # кэш на 2 минуты

# Глобальный кэш
user_cache: Dict[str, Dict] = {}
cache_time: Dict[str, float] = {}
locks: Dict[str, asyncio.Lock] = {}  # защита от одновременной записи

TTL_SECONDS = 120 # 2 минуты — хранится кэш


# Функция для очистки кэша (можно вызывать после создания/продления подписки)
async def invalidate_user_cache(telegram_id: str):
    lock = locks.setdefault(telegram_id,asyncio.Lock())
    async with lock:
        user_cache.pop(telegram_id, None)
        cache_time.pop(telegram_id, None)


#Найти пользователя по telegram_id
async def get_user(telegram_id: str) -> Optional[dict]:
    # cached_user = user_cache.get(telegram_id)
    # if cached_user:
    #     return cached_user

    # 1. Проверяем кэш под блокировкой
    lock = locks.setdefault(telegram_id, asyncio.Lock())
    async with lock:
        now = datetime.utcnow().timestamp()
        if (telegram_id in user_cache and
                now - cache_time.get(telegram_id, 0) < TTL_SECONDS):
            return user_cache[telegram_id]
    # 2. Если в кэше нет или устарел — идём в Remnawave
    try:
        response: TelegramUserResponseDto =await remnawave.users.get_users_by_telegram_id(telegram_id)
        if not response:
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
        # user_cache.set(telegram_id, user)
        return  user # возвращаем словарь - информация о пользователе
    except Exception as e:
        print(f"Ошибка при получении пользователя {telegram_id}: {e}")
        return None


# Создание пользователя и выдача пробного периода
async def create_new_user(username: str,
                      expire_days: int = 3,
                      traffic_limit_bytes: int = 10,
                      telegram_id: Optional[str] = None,
                      email: Optional[str] = None,
                      active_internal_squads: list = None,
                      note: str = "",
                      hwid_limit: int = 3):

        # Рассчитываем дату истечения
        expire_at = datetime.utcnow() + timedelta(days=expire_days)
        await remnawave.users.create_user(CreateUserRequestDto(
            username=f'{username}_{telegram_id}', # нужно уникольное имя комбинируем ник и tg_id
            active_internal_squads=["6002d566-a23d-40d4-82c7-624c2a7777b0","ecb4eace-49a3-4bdc-b9a7-190500b40e71"],
            expire_at=expire_at,  # обязательное поле
            telegram_id=telegram_id,
            email=email,
            description='Пробный период 3 дня',
            traffic_limit_bytes=traffic_limit_bytes * 1024 * 1024 * 1024 if traffic_limit_bytes > 0 else 0,  # в байтах
            hwid_device_limit=hwid_limit,
            status="ACTIVE",
            traffic_limit_strategy="MONTH"))
        user : TelegramUserResponseDto = await remnawave.users.get_users_by_telegram_id(telegram_id)
        url_sub = user.root[0].model_dump()['subscription_url']
        return url_sub


# После оплаты прибавляем пользователю длительность подписки (дни)
async def add_days(telegram_id: str, days:int):
    # # 1. Проверяем кэш под блокировкой
    # lock = locks.setdefault(telegram_id, asyncio.Lock())
    # async with lock:
    #     now = datetime.utcnow().timestamp()
    #     if (telegram_id in user_cache and
    #             now - cache_time.get(telegram_id, 0) < TTL_SECONDS):
    #         return user_cache[telegram_id]
    # # 2. Если в кэше нет или устарел — идём в Remnawave
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
        return True
    except Exception as e:
        print(f"Ошибка при получении пользователя {telegram_id}: {e}")
        return None



# Преобразование даты окончания подписки в норм вид
def format_expire_date(expire_str: datetime) -> str:
    if not expire_str:
        return "—"
    """Красиво форматирует дату окончания подписки"""
    try:
        # Форматируем в удобный вид
        return expire_str.strftime("%d.%m.%Y %H:%M")
        # Примеры вывода:
        # 07 апреля 2026, 06:41
        # 15 мая 2026, 23:59
    except:
        return "—"



#для тестирования
async def main():
 # Fetch all users

    await add_days('758504107',10)

    response: UsersResponseDto = await remnawave.users.get_users_by_telegram_id('758504107')
    # total_users: int = response.total
    # users: list[UserResponseDto] = response.users
    # print("Total users: ", total_users)
    # print("List of users: ", users)


    user = response.root[0].model_dump()
    print(user['uuid'])

    devices: HwidUserDeviceDto = await remnawave.hwid.get_hwid_user('7c2738ca-dce1-44b3-8bcb-6a2b000ee217')

    print(devices.devices)
    print(len(devices.devices))


    data = await get_user('758504107')
    print("DATA:", data['uuid'])

     # Сохранение users.json с панели remnawave_client
    with open('../cache/users_1.txt', 'w', encoding='utf-8') as file:
     file.writelines(data)


if __name__ == "__main__":
 asyncio.run(main())
