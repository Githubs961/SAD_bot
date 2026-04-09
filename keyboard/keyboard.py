from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import BotCommand
from aiogram import Bot
from lexicon.lexicon import LEXICON_COMMANDS, PLANS


# Создание меню бота
async def set_main_menu(bot: Bot):
    main_menu = [BotCommand(command=com,
                            description=des)
                 for com, des in LEXICON_COMMANDS.items()]
    await bot.set_my_commands(main_menu)


# Создаем объект главной клавиатуры
keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='🔐 Получить доступ')],
        [KeyboardButton(text='🏡 Личный кабинет'),KeyboardButton(text='ℹ️ Инструкция')]

    ],
    resize_keyboard=True,
    is_persistent=True)# Постоянно показывать клавиатуру
    # one_time_keyboard=False #Скрыть клавиатуру


# Создание инлайн клавиатуру для Подписок
sub_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text='7 дней  49 ₽', callback_data='sub_1w')],
        [InlineKeyboardButton(text='1 месяц 149 ₽', callback_data='sub_1m')],
        [InlineKeyboardButton(text='2 месяца 249 ₽', callback_data='sub_2m')]
    ]
)


# Клавиатура для оплаты, после выбора подписки. Функция принимает значение длительности подписки
def pay_keyboard(plan: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 СБП", callback_data=f"paysbp_{plan}")],
            [InlineKeyboardButton(text="⭐ Telegram Stars", callback_data=f"pay_{plan}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
        ]
    )


# Инлайн клавиатура - Личный кабинет
def profile_keyboard(sub_url):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📲 Подключить устройство", callback_data="add_device",url=sub_url)],
            [InlineKeyboardButton(text="📱 Мои устройства", callback_data="my_devices")]
        ]
    )