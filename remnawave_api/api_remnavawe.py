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
                              CreateInternalSquadRequestDto, TelegramUserResponseDto)


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
cache_lock = asyncio.Lock()  # защита от одновременной записи

TTL_SECONDS = 180 # 3 минуты — хранится кэш


# Функция для очистки кэша (можно вызывать после создания/продления подписки)
async def delete_user_cache(telegram_id: str):
    async with cache_lock:
        user_cache.pop(telegram_id, None)
        cache_time.pop(telegram_id, None)


#Найти пользователя по telegram_id
async def get_user_by_telegram_id(telegram_id: str) -> Optional[dict]:
    # cached_user = user_cache.get(telegram_id)
    # if cached_user:
    #     return cached_user
    # 1. Проверяем кэш под блокировкой
    async with cache_lock:
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

        # Сохраняем в кэш
        async with cache_lock:
            user_cache[telegram_id] = user
            cache_time[telegram_id] = datetime.utcnow().timestamp()
        # user_cache.set(telegram_id, user)
        return  user # возвращаем словать - информация о пользователе
    except Exception as e:
        print(f"Ошибка при получении пользователя {telegram_id}: {e}")
        return None


# Создание пользователя и выдача пробного периода
async def create_free_user(username: str,
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
            active_internal_squads=["6002d566-a23d-40d4-82c7-624c2a7777b0"],
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


# #Информация о пользовалеле
# async def personal_account(telegram_id: Optional[str] = None):




async def main():
 # Fetch all users
    response: UsersResponseDto = await remnawave.users.get_all_users()
    total_users: int = response.total
    users: list[UserResponseDto] = response.users
    print("Total users: ", total_users)
    print("List of users: ", users)


    # asd = await remnawave.users.get_users_by_telegram_id('758504107')
    # print(asd.model_dump_json())
    data = await get_user_by_telegram_id('758504107')
    print("DATA:",data['uuid'])




    async def create_user(remnawave,# экземпляр RemnawaveSDK
                          username: str,
                          expire_days: int = 30,
                          data_limit_gb: int = 0,
                          telegram_id: Optional[int] = None,
                          email: Optional[str] = None,
                          note: str = "",
                          hwid_limit: int = 3):
        """
         Удобная функция для создания пользователя
         """
     # Рассчитываем дату истечения
        expire_at = datetime.utcnow() + timedelta(days=expire_days)

    expire_at = datetime.utcnow() + timedelta(days=10)
    # await remnawave.users.create_user(CreateUserRequestDto(username="usernames_23432",
    #         expire_at=expire_at,  # обязательное поле
    #         telegram_id=41414412,
    #         email=None,
    #         description='note',
    #         traffic_limit_bytes=10,  # в байтах
    #         hwid_device_limit=2,
    #         status="ACTIVE",  # или UserStatus.ACTIVE
    #         traffic_limit_strategy="NO_RESET"))


if __name__ == "__main__":
 asyncio.run(main())
