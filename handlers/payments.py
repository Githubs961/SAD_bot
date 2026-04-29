import asyncio
from aiogram import Router, F, Bot
from aiogram.client import bot
from aiogram.types import CallbackQuery, LabeledPrice, PreCheckoutQuery, Message, InlineKeyboardMarkup, \
    InlineKeyboardButton
from aiogram.filters import Command, CommandObject
from aiogram.utils.markdown import hlink

from database import save_payment, get_active_payment, update_db, get_db_connection, db_lock
from handlers.admins import admin_filter
from keyboard.keyboard import sub_keyboard
from lexicon.lexicon import PAY_STARS, PLANS, PAY_SBP, DAYS, PAYMENT_STATUS_MESSAGES, KONF, SOGL, PAYMENT_SEC
from remnawave_api.api_remnavawe import invalidate_user_cache, add_days
import uuid
import os
from dotenv import load_dotenv
from platega import Platega

from services.services import reset_traffic, enable_user_squad

MERCHANT_ID = os.getenv('MERCHANT_ID')
PLATEGA_API = os.getenv('PLATEGA_API')

# Инициализируем роутер
payments_router = Router()


#Подключение к Platega.io
platega = Platega(merchant_id=MERCHANT_ID,secret=PLATEGA_API)



# Обработчик оплаты Telegram Stars
@payments_router.callback_query(F.data.in_(PAY_STARS.keys()))
async def pay_stars(callback: CallbackQuery):
    plan = callback.data
    sub_text = f'sub_{plan.split("_")[1]}' # переменная для текста из lexicon.py
    prices = [LabeledPrice(label='XTR', amount=PAY_STARS[plan])]

    await callback.message.delete() # удаляю предыдущее сообщение
    await callback.message.answer_invoice(
        title=f'VPN подписка',
        description=f'Тариф: {PLANS[sub_text]}',
        payload=plan, # важно! желательно уникальный payload
        currency='XTR',
        prices=prices,
        # is_test= True,  # ← Вот это главное для теста!
    )


    await callback.answer()



# Подтверждение платежа и проверка есть ли подписка STARS
@payments_router.pre_checkout_query()
async def pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await pre_checkout_q.answer(ok=True)



# Проверка оплаты и выдача подписки STARS
@payments_router.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment
    user_id = message.from_user.id
    plan_key = payment.invoice_payload
    transactionId = payment.telegram_payment_charge_id

    try:
        # 1. Сохраняем платёж
        saved = await save_payment(

            user_id=user_id,
            transactionId=transactionId,
            plan_key=plan_key,
            amount=payment.total_amount,
            provider= 'STARS',
            status='CONFIRMED',
            currency=payment.currency
        )

        if not saved:
            await message.answer("Этот платёж уже был обработан ранее.")
            return

        # 2. Выдаём подписку
        success = await add_days(telegram_id=str(user_id),days=DAYS[plan_key]) # количество дней добавленных к подписке

        async with db_lock:
            # 3. Обнуляем трафик пользователю
            await reset_traffic(user_id)

            # 4. Включаю скваду Яндекс если отключена
            await enable_user_squad(user_id)


        if success:
            await message.answer(
                f"✅ Оплата прошла успешно!\n"
                f"Подписка активирована.\n\n"
                f"Проверьте Личный кабинет"
            )
            # # Очищаем кэш пользователя( перенес функцию в addd days)
            # await invalidate_user_cache(str(user_id))
        else:
            await message.answer("❌ Ошибка активации подписки. Обратитесь в поддержку.")

    except Exception as e:
        print(f"Ошибка обработки платежа: {e}")
        await message.answer("❌ Произошла ошибка. Обратитесь в поддержку.")



# Возврат STARS по id транзакции(refund пробел transaction_id)
@payments_router.message(Command('refund'),admin_filter)
async def command_refund(message: Message, bot: Bot, command: CommandObject) -> None:
    transaction_id = command.args
    try:
        await  bot.refund_star_payment(
            user_id=message.from_user.id,
            telegram_payment_charge_id=transaction_id
        )
    except Exception as e:
        print(e)




# СБП Создание платежа(через Platega)
@payments_router.callback_query(F.data.in_(PAY_SBP.keys()))
async def pay_sbp(callback: CallbackQuery):
    plan = callback.data
    sub_text = f'sub_{plan.split("_")[1]}'  # переменная для текста из lexicon.py

    # 1. ищем существующий платеж
    existing = get_active_payment(callback.from_user.id, plan)
    if existing:
        payment_url = existing["redirect"]
        transaction_id = existing["transactionId"]
        #payment_url = platega.get_payment_status(existing["transactionId"])["redirect"]
    # 2. Если нет , то создаем платеж
    else:
        payment = platega.create_payment(

            amount=PAY_SBP[plan],
            currency="RUB",
            payment_method=Platega.METHOD_SBP_QR,
            description=f"Подписка {PLANS[sub_text]}",
            payload=str(uuid.uuid4())  # ОЧЕНЬ ВАЖНО уникальный
        )
        await save_payment(
            user_id=callback.from_user.id,
            provider="Platega",
            status="PENDING",
            transactionId=payment["transactionId"],
            plan_key=plan,
            amount=PAY_SBP[plan],
            currency="RUB",
            redirect=payment["redirect"]
        )

        payment_url = payment["redirect"]
        transaction_id = payment["transactionId"] # для проверки оплаты
    # кнопка проверить статус(можно сделать) или сделать функцию которая будет проверять

    # status = platega.get_payment_status(payment["transactionId"])
    # if Platega.is_success_status(status["status"]):
    # ✅ выдать доступ


    await callback.message.answer(f"{hlink(title='Политика конфиденциальности',url=KONF)}\n"
                                  f"{hlink(title='Пользовательское соглашение',url=SOGL)}\n\n"
                                  f"💳 Оплата подписки {PLANS[sub_text]}:", disable_web_page_preview=True,
    reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="💰 Оплатить",
                url=payment_url
            )],
            [InlineKeyboardButton(
                text="🔄 Проверить оплату",
                callback_data=f"check_{transaction_id}"
            )]
            # ,
            # [InlineKeyboardButton(
            #     text="❌ Отмена",
            #     callback_data=sub_text #Возвращаемся в тот тариф который выбирали
            # )]
        ]
    )
    )
    await callback.answer()



# Проверка оплаты Platega
@payments_router.callback_query(F.data.startswith("check_"))
async def check_payment(callback: CallbackQuery):
    transaction_id = callback.data.split("_")[1]

    status_data = platega.get_payment_status(transaction_id)
    status = status_data["status"]

    row = update_db(status, transaction_id)

    if not row:
        await callback.answer("❌ Платёж не найден", show_alert=True)
        return

    # ✅ УСПЕХ
    if Platega.is_success_status(status):

        if row["old_status"] == "CONFIRMED":
            await callback.answer("⚠️ Уже оплачено", show_alert=True)
            return

        user_id = row["user_id"]
        plan_key = row["plan_key"]

        # Добавляем подписку
        await add_days(
            telegram_id=str(user_id),
            days=DAYS[plan_key]
        )

        async with db_lock:
            #Обнуляем трафик пользователю
            await reset_traffic(user_id)

            # Включаю скваду Яндекс если отключена
            await enable_user_squad(user_id)

        await callback.message.edit_text(
            PAYMENT_STATUS_MESSAGES[status]
        )
        return

    # ⏳ ОЖИДАНИЕ (без спама)
    if status == "PENDING":
        await callback.answer(
            PAYMENT_STATUS_MESSAGES[status],
            show_alert=True
        )
        return
    if status == "EXPIRED":
        await callback.answer("⌛ Платёж устарел, создайте новый", show_alert=True)
        return

    # ❌ ОТМЕНА / ОШИБКА
    try:
        await callback.message.edit_text(
            PAYMENT_STATUS_MESSAGES.get(status, f"Статус: {status}")
        )
    except:
        pass
    await callback.answer()




# автопроверка оплаты Platega
async def auto_check_payments(bot):
    while True:
        print('Проверяю оплату')
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT transactionId, user_id, plan_key
            FROM payments
            WHERE status = 'PENDING'
            AND created_at > datetime('now', '-30 minutes')
        """)

        payments = cursor.fetchall()
        conn.close()

        for p in payments:
            try:
                status_data = platega.get_payment_status(p["transactionId"])
                status = status_data["status"]

                row = update_db(status, p["transactionId"])

                if status == "CONFIRMED" and row and row["old_status"] != "CONFIRMED":
                    #Выдача подписки
                    await add_days(
                        telegram_id=str(p["user_id"]),
                        days=DAYS[p["plan_key"]]
                    )

                    async with db_lock:
                        # Обнуляем трафик пользователю
                        await reset_traffic(p["user_id"])

                        # Включаю скваду Яндекс если отключена
                        await enable_user_squad(p["user_id"])


                    # 👉 уведомляем пользователя
                    await bot.send_message(
                        chat_id=p["user_id"],
                        text="✅ Оплата прошла! Подписка активирована"
                    )

            except Exception as e:
                print("auto_check error:", e)

        await asyncio.sleep(PAYMENT_SEC)  # ЧАСТОТА ПРОВЕРКИ ПЛАТЕЖА в сек



