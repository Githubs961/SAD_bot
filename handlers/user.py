from aiogram import Router, types, Bot
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice, InlineKeyboardButton, \
    InlineKeyboardMarkup
from aiogram.filters import Command, CommandStart, or_f, CommandObject
from aiogram import F
from datetime import datetime
from aiogram.utils.markdown import hlink

from database import save_user, get_user_traffic, save_referral, get_referral_stats
from remnawave_api.api_remnavawe import (get_user,
                                         create_new_user,
                                         format_expire_date, delete_user_device, invalidate_user_cache)
from keyboard.keyboard import keyboard, sub_keyboard, pay_keyboard, profile_keyboard, instruction_keyboard, \
    devices_keyboard, delete_device_keyboard
from lexicon.lexicon import LEXICON_RU, PLANS, PAY_STARS, INSTRUCTION
from services.services import init_traffic

# Инициализируем роутер уровня модуля
router = Router()



#Обработка команды Start
@router.message(CommandStart())
async def process_start_command(message: Message,
                                command: CommandObject):
    ref_code = command.args

    if ref_code and ref_code.startswith("ref_"):

        try:
            referrer_id = int(ref_code.replace("ref_", ""))
            referred_id = message.from_user.id

            if await save_referral(
                    referrer_id=referrer_id,
                    referred_id=referred_id
            ):
                print(
                    f"🎁 Новый реферал "
                    f"{referrer_id} -> {referred_id}"
                )

        except Exception as e:
            print(f"Referral error: {e}")

    await message.answer(
        text=LEXICON_RU['/start'],
        reply_markup=keyboard,
        disable_web_page_preview=True
    )





@router.message(or_f(F.text == "🔐 Получить доступ", Command("access")))
async def subscription_list(message: Message):
    # Проверка что нет пользователя с таким tg_id и после выдать пробную подписку
    if not await get_user(str(message.from_user.id)): #если пользователя нет то создаем
        user = await create_new_user(telegram_id=str(message.from_user.id),
                                         username=message.from_user.username)# дынные пользователя
        if user:
            await save_user(
                user_id=int(message.from_user.id),
                username=user["username"],
                uuid=user["uuid"]
            )
            # Запись в БД для подсчета трафика
            await init_traffic(int(message.from_user.id))
        await message.answer(text=f'🎁 Пробный период 3 дня активирован\n\nДля подключения перейдите в\n 🏡 Личный кабинет ',# Ссылка для подключения:\n{sub_url}
                             reply_markup=sub_keyboard)
    else:
        await message.answer(text= LEXICON_RU['subscription'],
                             reply_markup=sub_keyboard)



@router.message(or_f(F.text == "🏡 Личный кабинет", Command("profile"))) #or Command(commands='profile')
async def show_profile(message: Message):
    # Отправляем сообщение-загрузку
    # loading_msg = await message.answer("⏳ Загружаю данные вашего профиля...")

    user = await get_user(str(message.from_user.id))
    # если пользователь найден
    if user:
        await init_traffic(message.from_user.id)
        traffic = get_user_traffic(message.from_user.id)

        # ✅ Проверка на None
        if traffic and traffic["used_bytes"] is not None:
            used_gb = round(traffic["used_bytes"] / 1024 ** 3, 2)
            limit_gb = round(traffic["traffic_limit"] / 1024 ** 3, 2)
        else:
            used_gb = 0
            limit_gb = 0
        await message.answer(text= f"🆔 <b>ID:</b> {user['username']}\n\n"
                                   f"⚠️<b>Статус подписки:</b> {user['status']}\n"
                                   f" └  Действует до: {format_expire_date(user['expire_at'])}\n\n"
                                   f"📊 <b>Трафик:</b>\n"
                                   f" ├  Обычные локации - ♾️ GB\n"
                                   f" └  LTE - {used_gb} / {limit_gb} GB\n\n"
                                   f"📱 <b>Лимит устройств:</b> {user['hwid_device_limit']}\n\n",
                             reply_markup=profile_keyboard(user['subscription_url']),
                             disable_web_page_preview=True
                         )
    if not user:
        await message.answer(text='❌ У вас нет действующей подписки\n '
                                  '🔒 Получите доступ')



# Обработчик кнопки "Назад" в личный кабинет
@router.callback_query(F.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery):
    user = await get_user(str(callback.from_user.id))

    if user:
        # Редактируем текущее сообщение (то, где был список устройств)
        # и показываем в нём профиль
        traffic = get_user_traffic(callback.from_user.id)

        # ✅ Проверка на None
        if traffic and traffic["used_bytes"] is not None:
            used_gb = round(traffic["used_bytes"] / 1024 ** 3, 2)
            limit_gb = round(traffic["traffic_limit"] / 1024 ** 3, 2)
        else:
            used_gb = 0
            limit_gb = 0
        await callback.message.edit_text(text=f"🆔 <b>ID:</b> {user['username']}\n\n"
                                              f"⚠️<b>Статус подписки:</b> {user['status']}\n"
                                              f" └  Действует до: {format_expire_date(user['expire_at'])}\n\n"
                                              f"📊 <b>Трафик:</b>\n"
                                              f" ├  Обычные локации - ♾️ GB\n"
                                              f" └  LTE - {used_gb} / {limit_gb} GB\n\n"
                                              f"📱 <b>Лимит устройств:</b> {user['hwid_device_limit']}",
            reply_markup=profile_keyboard(user['subscription_url']),
            disable_web_page_preview=True,
            parse_mode="HTML"
        )
    if not user:
        await callback.message.edit_text(
            text='❌ У вас нет действующей подписки\n🔒 Получите доступ'
        )

    await callback.answer()



@router.message(or_f(F.text == 'ℹ️ Инструкция',Command('help')))
async def manual(message: Message):
    await message.answer(text= f'{INSTRUCTION["step_1"]}',

                         reply_markup=instruction_keyboard(1),
                         disable_web_page_preview=True
                         )



# Обработка нажатий на клавиатуру инструкции
@router.callback_query(F.data.startswith("instruction:"))
async def navigate_instruction(callback: CallbackQuery):
    step = int(callback.data.split(":")[1])

    await callback.message.edit_text(
        INSTRUCTION[f"step_{step}"],
        reply_markup=instruction_keyboard(step),
        parse_mode="HTML"
    )

    await callback.answer()


# Обработка при выборе длительности подписки
@router.callback_query(F.data.in_(PLANS.keys()))
async def sub_duration(callback: CallbackQuery):
    plan = callback.data # какую подписку выбрал пользователь при нажатии на инлайн кнопку
    await callback.message.edit_text(text=f'Вы выбрали подписку: {PLANS[plan]}\nСпособ оплаты 👇',
                                         reply_markup=pay_keyboard(plan.split('_')[1]))
                                        # функция pay_keyboard принимает значение длительности подписки
    await callback.answer()


# Обработчик кнопки back
@router.callback_query(F.data == 'back')
async def click_back(callback: CallbackQuery):
    await callback.message.edit_text(text= LEXICON_RU['subscription'],
                                     reply_markup=sub_keyboard
                                     )
    await callback.answer()



# 🎁 Реферальная программа
@router.callback_query(F.data == "referral")
async def referral_menu(callback: CallbackQuery):
    tg_id = callback.from_user.id

    # Получаем статистику через отдельную функцию
    stats = await get_referral_stats(tg_id)

    referral_link = f"https://t.me/SADNetwork_bot?start=ref_{tg_id}"

    text = (
        f"🎁 <b>Реферальная программа</b>\n\n"
        f"Пригласите друга и получите +15 дней подписки после его первой оплаты.\n\n"
        f"🔗 Ваша ссылка:\n\n"
        f"<code>{referral_link}</code>\n\n"
        f"👥 Приглашено друзей: <b>{stats['total']}</b>\n"
        f"✅ Получено наград: <b>{stats['rewarded']}</b>"
    )

    # Создаём клавиатуру с кнопкой Назад
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="back_to_profile"
                )
            ]
        ]
    )

    await callback.message.edit_text(
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()




# обработка кнопки "Мои устройства"
@router.callback_query(F.data == 'my_devices')
async def click_add_device(callback: CallbackQuery):
    user = await get_user(str(callback.from_user.id))
    devices = user['devices']
    if not devices:
        await callback.answer("У вас нет подключённых устройств", show_alert=True)
        return
    if devices: # не верная проверка на устройства нужно перепроверить
        text = '📱 <b>Ваши устройства</b>\n\n'
        for i, dev in enumerate(devices,1): # dev это объект поэтому обращаемся через . а не  dev['device_model']
            device_model = dev.get('deviceModel', 'Unknown') or dev.get('device_model', 'Unknown')
            user_agent = dev.get('userAgent', 'Unknown') or dev.get('user_agent', 'Unknown')
            created_at = dev.get('createdAt', None) or dev.get('created_at', None)

            # Форматируем дату
            if created_at:
                try:
                    if isinstance(created_at, str):
                        created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    created_str = created_at.strftime('%d.%m.%Y %H:%M')
                except:
                    created_str = str(created_at)
            else:
                created_str = 'Неизвестно'

            text += f"<b>{i}. {device_model}</b>\n"
            text += f"   Приложение: {user_agent[:30]}...\n" if len(
                user_agent) > 30 else f"   Приложение: {user_agent}\n"
            text += f"   Добавлено: {created_str}\n\n"

        await callback.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup= devices_keyboard(devices)
        )
        await callback.answer()



# Подтверждение удаления устройства
@router.callback_query(F.data.startswith("confirm_delete:"))
async def confirm_delete_device(callback: CallbackQuery):
    hwid = callback.data.split(":", 1)[1]

    user = await get_user(str(callback.from_user.id))

    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    # 🔥 ИСПРАВЛЕНО: поиск по словарю
    device = next(
        (d for d in user.get("devices", []) if d.get("hwid") == hwid),
        None
    )

    if not device:
        await callback.answer("Устройство не найдено", show_alert=True)
        return

    # 🔥 ИСПРАВЛЕНО: обращаемся по ключам
    device_model = device.get('deviceModel', 'Unknown') or device.get('device_model', 'Unknown')
    platform = device.get('platform', 'Unknown')

    await callback.message.edit_text(
        text=(
            f"⚠️ <b>Удалить устройство?</b>\n\n"
            f"📱 {device_model}\n"
            f"🖥 {platform}\n\n"
        ),
        parse_mode="HTML",
        reply_markup=delete_device_keyboard(hwid)  # Исправлено название функции
    )
    await callback.answer()


# Удаление устройства и возврат в Личный кабинет
@router.callback_query(F.data.startswith("delete_device:"))
async def delete_device(callback: CallbackQuery):
    hwid = callback.data.split(":", 1)[1]

    user = await get_user(str(callback.from_user.id))

    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    # Вызываем API remnawave
    success = await delete_user_device(
        telegram_id=str(callback.from_user.id),
        user_uuid=user["uuid"],
        hwid=hwid
    )

    if not success:
        await callback.answer("❌ Ошибка удаления устройства", show_alert=True)
        return

    # Очищаем кэш
    await invalidate_user_cache(str(callback.from_user.id))

    # Получаем обновлённого пользователя
    user = await get_user(str(callback.from_user.id))

    traffic = get_user_traffic(callback.from_user.id)

    if traffic and traffic["used_bytes"] is not None:
        used_gb = round(traffic["used_bytes"] / 1024 ** 3, 2)
        limit_gb = round(traffic["traffic_limit"] / 1024 ** 3, 2)
    else:
        used_gb = 0
        limit_gb = 0

    await callback.message.edit_text(
        text=f"🆔 <b>ID:</b> {user['username']}\n\n"
             f"⚠️<b>Статус подписки:</b> {user['status']}\n"
             f" └ Действует до: {format_expire_date(user['expire_at'])}\n\n"
             f"📊 <b>Трафик:</b>\n"
             f" ├ Обычные локации - ♾️ GB\n"
             f" └ LTE - {used_gb} / {limit_gb} GB\n\n"
             f"📱 <b>Лимит устройств:</b> {user['hwid_device_limit']}",
        parse_mode="HTML",
        reply_markup=profile_keyboard(user['subscription_url']),
        disable_web_page_preview=True
    )

    await callback.answer("✅ Устройство удалено")