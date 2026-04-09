from aiogram import Router, types
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, LabeledPrice
from aiogram.filters import Command, CommandStart, or_f
from aiogram import F
from aiogram.utils.markdown import hlink
from remnawave_api.api_remnavawe import (get_user,
                                         create_new_user,
                                         format_expire_date)
from keyboard.keyboard import keyboard, sub_keyboard, pay_keyboard, profile_keyboard
from lexicon.lexicon import LEXICON_RU, PLANS, PAY_STARS


# Инициализируем роутер уровня модуля
router = Router()

@router.message(CommandStart())
async def process_start_command(message: Message):
   # if await is_admin(message.chat.id):
        await message.answer(text=LEXICON_RU['/start'],
                             reply_markup=keyboard)


@router.message(Command(commands='help'))
async def process_help_command(message: Message):
    await message.answer(text=LEXICON_RU['/help'],
                         disable_web_page_preview=True
                         )

#
@router.message(or_f(F.text == "🔐 Получить доступ", Command("access")))
async def subscription_list(message: Message):
    # Проверка что нет пользователя с таким tg_id и после выдать пробную подписку
    if not await get_user(str(message.from_user.id)): #если пользователя нет то создаем
        sub_url = await create_new_user(telegram_id=str(message.from_user.id),
                                         username=message.from_user.username)# ссылка для подключения
        await message.answer(text=f'🎁 Пробный период 3 дня активирован\n🔗 Ссылка для подключения:\n{sub_url}',
                             reply_markup=sub_keyboard)
    else:
        await message.answer(text= LEXICON_RU['subscription'],
                             reply_markup=sub_keyboard)


@router.callback_query(F.data == "profile")
@router.message(or_f(F.text == "🏡 Личный кабинет", Command("profile"))) #or Command(commands='profile')
async def show_profile(message: Message):
    user = await get_user(str(message.from_user.id))
    # если пользователь найден
    if user:
        await message.answer(text= f"🔹<b>Логин:</b> {user['username']}\n"
                                   f"❗️<b>Статус подписки:</b> {user['status']}\n"
                                   f"📅<b> Действует до:</b> {format_expire_date(user['expire_at'])}\n"
                                   f"📱 <b>Лимит устройств:</b> {user['hwid_device_limit']}",
                             reply_markup=profile_keyboard(user['subscription_url']),
                             disable_web_page_preview=True
                         )
    else:
        await message.answer(text='❌ У вас нет действующей подписки\n '
                                  '🔒 Получите доступ')



@router.message(F.text == 'ℹ️ Инструкция')
async def manual(message: Message):
    await message.answer(text= LEXICON_RU['/help'],
                         disable_web_page_preview=True
                         )

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


# обраюотка кнопки "Мои устройства"
@router.callback_query(F.data == 'my_devices')
async def click_add_device(callback: CallbackQuery):
    user = await get_user(str(callback.from_user.id))
    devices = user['devices']
    if not devices:
        await callback.answer("У вас пока нет подключённых устройств", show_alert=True)
        return
    if devices: # не верная проверка на устройства нужно перепроверить
        text = ''
        for i, dev in enumerate(devices,1): # dev это объект поэтому обращаемся через . а не  dev['device_model']
            text += f"{i}. <b>{str(dev.device_model)}</b>\n"
            text += f"   Приложение: {dev.user_agent}\n"
            text += f"   Добавлено: {dev.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        # # Кнопка возврата в личный кабинет
        # keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        #     [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="/profile")]
        # ])
        await callback.message.answer(text=text,parse_mode="HTML")

    await callback.answer()



# Обработчик оплаты Telegram Stars
@router.callback_query(F.data.in_(PAY_STARS.keys()))
async def pay_stars(callback: CallbackQuery):
    plan = callback.data
    sub_text = f'sub_{plan.split("_")[1]}' # переменная для текста из lexicon.py
    prices = [LabeledPrice(label='XTR', amount=PAY_STARS[plan])]

    await callback.message.answer_invoice(
        title=f'VPN подписка',
        description=f'Тариф: {PLANS[sub_text]}',
        payload=plan,
        currency='XTR',
        prices=prices
    )
    await callback.answer()


# Подтверждение платежа и проверка есть ли подписка
@router.pre_checkout_query()
async def pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await pre_checkout_q.answer(ok=True)


# Проверка что платеж прошел и выполняем условие.....
@router.message(F.succeful_payment)
async def payment(message:Message):
    await message.answer(f'{message.successful_payment.telegram_payment_charge_id}')