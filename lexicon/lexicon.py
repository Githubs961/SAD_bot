from typing import Dict

from aiogram.utils.markdown import hlink

IOS = 'https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973' #Ссылка на HAPP
ANDROID = 'https://play.google.com/store/apps/details?id=com.happproxy' #Ссылка на HAPP

KONF = 'https://telegra.ph/Politika-konfidencialnosti-04-01-26'
SOGL = 'https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19'

#Автопроверка трафика в фоне в сек
TRAFFIC_SEC: int = 18 #
# ЧАСТОТА ПРОВЕРКИ ПЛАТЕЖА в сек
PAYMENT_SEC: int = 120


LEXICON_COMMANDS: dict[str, str] = {
    '/start': 'Начало работы с ботом',
    '/access': 'Получить доступ',
    '/profile': 'Личный кабинет',
    '/help': 'Инструкция'
}


LEXICON_RU: dict[str, str] = {
    '/start': f'<b>Добро пожаловать в SAD Network</b>\n\n'
              f'Ваш надёжный доступ к приватной сети. \n\n'
              f'<b>Приемущества:</b>\n\n'
              f'⛔️ Без рекламы\n'
              f'♾️ Безлимит(Wi-Fi)\n'
              f'🔒 Защищённое соединение\n'
              f'📱 Поддержка всех устройств\n\n',

    'subscription': '<b>Что входит:</b>\n'
                    '✅ Безлимит на обычные локации\n'
                    '✅ LTE: 50 ГБ/месяц\n'
                    '✅ Устройств в подписке: 3\n\n'
                    '<b>Выберите тариф для подключения</b>'
}

PLANS = {
    "sub_1w": "🗓 7 дней",
    "sub_1m": "🗓 1 месяц",
    "sub_2m": "🗓 2 месяца",
}
PAY_STARS = {
    "pay_1w": 3,
    "pay_1m": 9,
    "pay_2m": 15,
}
PAY_SBP = {
    "paysbp_1w": 49,
    "paysbp_1m": 149,
    "paysbp_2m": 249,
}
DAYS = {
    "pay_1w": 7,
    "pay_1m": 30,
    "pay_2m": 60,
    "paysbp_1w": 7,
    "paysbp_1m": 30,
    "paysbp_2m": 60
}

PAYMENT_STATUS_MESSAGES = {
    "CONFIRMED": "✅ Оплата прошла! Подписка активирована",
    "PENDING": "⏳ Платёж ещё не завершён.",
    "CANCELED": "❌ Платёж отменён",
    "CHARGEBACKED": "⚠️ Платёж отозван (chargeback)",
}



INSTRUCTION: dict[str, str] = {
    'step_1': f'После получения доступа в Личном кабинете кликните "🔗 Подключить устройство" откроется страница подписки:\n\n'
              f'<b>🧩 Шаг 1. Установите приложение</b>\n\n'
              f'В блоке «Установка» выберите:\n'
              f'ваше устройство (IOS / Android / Windows)\n'
              f'приложение (например HAPP)\n'
              f'Нажмите кнопку <b>«Установить»</b>(App Store / Google Play / Скачать APK)'
    ,
    'step_2': f'🔗 <b>Шаг 2. Добавьте подписку</b>\n\n'
              f'После установки:\n'
              f'Нажмите кнопку <b>«Добавить подписку»</b>\n'
              f'Подписка автоматически добавится в приложение\n\n'
              f'✅ Ничего копировать не нужно'
    ,
    'step_3': f'📲 <b>Альтернативный способ</b> (скопировать вручную)\n\n'
              f'Нажмите на значок 🔗 (ссылка)\n'
              f'Скопируйте ссылку\n'
              f'Вставьте в приложение'
    ,
    'step_4': f'📷 <b>Через QR-код</b>\n\n'
              f'Нажмите на значок 🔗\n'
              f'Откройте QR-код\n'
              f'Отсканируйте его в приложении'
    ,
    'step_5': f'💬 Нужна помощь?'
              f'Напишите в поддержку — поможем подключиться 🙌 '
              f'@monako113'
}


