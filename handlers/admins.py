import asyncio

from dotenv import load_dotenv
from aiogram.filters import BaseFilter, Command
from aiogram.types import Message, BufferedInputFile
import os
from database import get_db_connection
from handlers.user import router
import csv
import io
from datetime import datetime
from remnawave_api.api_remnavawe import remnawave
IDS = os.getenv('ADMINS_ID')

# Проверка на админку по ID
class AdminFilter(BaseFilter):
    """Фильтр для проверки, является ли пользователь админом"""
    async def __call__(self, message: Message) -> bool:
        return str(message.from_user.id) in IDS

# Объект фильтра
admin_filter = AdminFilter()




# Скачивание таблицы с платежами
@router.message(Command("db"), admin_filter)
async def db_check(message: Message):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем все платежи
    cursor.execute("""
        SELECT id, provider, status, user_id, transactionId, 
               plan_key, amount, currency, created_at, processed_at, redirect
        FROM payments 
        ORDER BY id DESC
    """)
    payments = cursor.fetchall()

    # Статистика по валютам
    cursor.execute("""
        SELECT currency, COUNT(*) as count, SUM(amount) as total
        FROM payments 
        WHERE status='CONFIRMED'
        GROUP BY currency
    """)
    stats_by_currency = cursor.fetchall()

    # Общая статистика
    cursor.execute("SELECT COUNT(*) as total FROM payments")
    total = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) as confirmed FROM payments WHERE status='CONFIRMED'")
    confirmed = cursor.fetchone()['confirmed']

    conn.close()

    # Формируем текст статистики для caption
    stats_text = f"📊 **Все платежи**\n\n"
    stats_text += f"💰 Всего платежей: {total}\n"
    stats_text += f"✅ Подтверждено: {confirmed}\n\n"

    if stats_by_currency:
        stats_text += f"💵 **Общая сумма по валютам:**\n"
        for stat in stats_by_currency:
            currency = stat['currency']
            amount = stat['total'] or 0
            count = stat['count']
            currency_name = "XTR" if currency == "XTR" else "₽" if currency == "RUB" else currency
            stats_text += f"└ {currency_name}: {amount} ({count} платежей)\n"

    stats_text += f"\n📅 Выгрузка: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
    stats_text += f"📁 Файл можно открыть в Excel или Google Sheets"

    # Создаем CSV файл
    output = io.StringIO()
    writer = csv.writer(output)

    # Заголовки
    writer.writerow([
        'ID', 'Provider', 'Status', 'User ID', 'Transaction ID',
        'Plan', 'Amount', 'Currency', 'Created At', 'Processed At', 'Redirect URL'
    ])

    # Данные
    for p in payments:
        writer.writerow([
            p['id'],
            p['provider'],
            p['status'],
            p['user_id'],
            p['transactionId'],
            p['plan_key'],
            p['amount'],
            p['currency'],
            p['created_at'],
            p['processed_at'] or '',
            p['redirect'] or ''
        ])

    # Формируем файл
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_bytes = output.getvalue().encode('utf-8-sig')
    file = BufferedInputFile(csv_bytes, filename=f"payments_{timestamp}.csv")

    # Отправляем
    await message.answer_document(
        document=file,
        caption=stats_text,
        parse_mode='Markdown'
    )




# Отправка сообщения всем пользователям
@router.message(Command("message"), admin_filter)
async def broadcast(message: Message):
    text = message.text.replace("/message", "").strip()

    if not text:
        await message.answer("❌ Укажите текст рассылки:\n\n`/message Ваш текст`", parse_mode="Markdown")
        return

    await message.answer("📨 Запускаю рассылку...")

    success = 0
    failed = 0
    blocked = 0
    total = 0

    try:
        # Получаем всех пользователей из Remnawave
        users_response = await remnawave.users.get_all_users()
        users = users_response.users  # это список UserResponseDto

        total = len(users)
        await message.answer(f"Найдено пользователей: {total}\nНачинаю отправку...")

        for user in users:
            if not user.telegram_id:
                continue

            try:
                await message.bot.send_message(
                    chat_id=int(user.telegram_id),
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                success += 1
                await asyncio.sleep(0.12)  # антифлуд

            except Exception as e:
                error_str = str(e).lower()
                if any(word in error_str for word in ["blocked", "forbidden", "chat not found", "deactivated"]):
                    blocked += 1
                else:
                    failed += 1
                print(f"Не отправлено {user.telegram_id}: {e}")

                if "flood" in error_str:
                    await asyncio.sleep(5)

        await message.answer(
            f"✅ <b>Рассылка завершена!</b>\n\n"
            f"Всего: {total}\n"
            f"✅ Доставлено: {success}\n"
            f"🚫 Заблокировали бота: {blocked}\n"
            f"❌ Другие ошибки: {failed}",
            parse_mode="HTML"
        )

    except Exception as e:
        await message.answer(f"❌ Критическая ошибка: {e}")
        print(f"Broadcast error: {e}")

