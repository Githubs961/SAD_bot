from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, LabeledPrice, PreCheckoutQuery, Message
from aiogram.filters import Command, CommandObject

from database import save_payment, grant_subscription
from lexicon.lexicon import PAY_STARS, PLANS, PAY_SBP, DAYS
from remnawave_api.api_remnavawe import invalidate_user_cache, add_days

# Инициализируем роутер
payments_router = Router()



# Обработчик оплаты Telegram Stars
@payments_router.callback_query(F.data.in_(PAY_STARS.keys()))
async def pay_stars(callback: CallbackQuery):
    plan = callback.data
    sub_text = f'sub_{plan.split("_")[1]}' # переменная для текста из lexicon.py
    prices = [LabeledPrice(label='XTR', amount=PAY_STARS[plan])]

    await callback.message.answer_invoice(
        title=f'VPN подписка',
        description=f'Тариф: {PLANS[sub_text]}',
        payload=plan, # важно! уникальный payload
        currency='XTR',
        prices=prices,
        # is_test= True,  # ← Вот это главное для теста!
    )
    await callback.answer()


# СБП (через payment.kassa.ai или другой агрегатор)
@payments_router.callback_query(F.data.in_(PAY_SBP.keys()))
async def pay_sbp(callback: CallbackQuery):
    plan = callback.data
    # Здесь будет вызов API агрегатора (payment.kassa.ai, ЮKassa, Тинькофф и т.д.)
    await callback.answer("🔄 Генерируем ссылку на оплату по СБП...", show_alert=True)

    # Пока заглушка
    await callback.message.answer(
        "💳 Оплата по СБП\n\n"
        "Сейчас мы генерируем ссылку...\n"
        "(Пока в разработке)"
    )





# Подтверждение платежа и проверка есть ли подписка
@payments_router.pre_checkout_query()
async def pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await pre_checkout_q.answer(ok=True)


# Возврат STARS по id транзакции(refund пробел transaction_id)
@payments_router.message(Command('refund'))
async def command_refund(message: Message, bot: Bot, command: CommandObject) -> None:
    transaction_id = command.args
    try:
        await  bot.refund_star_payment(
            user_id=message.from_user.id,
            telegram_payment_charge_id=transaction_id
        )
    except Exception as e:
        print(e)


# Проверка что платеж STARTS прошел и выполняем условие.....
# @payments_router.message(F.successful_payment)
# async def payment(message:Message):
#     await message.answer(f'{message.successful_payment.telegram_payment_charge_id}')


@payments_router.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment
    user_id = message.from_user.id
    plan_key = payment.invoice_payload
    charge_id = payment.telegram_payment_charge_id

    try:
        # 1. Сохраняем платёж
        saved = await save_payment(
            user_id=user_id,
            charge_id=charge_id,
            plan_key=plan_key,
            amount=payment.total_amount
        )

        if not saved:
            await message.answer("Этот платёж уже был обработан ранее.")
            return

        # 2. Выдаём подписку
        # success = await grant_subscription(
        #     user_id=user_id,
        #     plan_key=plan_key,
        #     telegram_id=user_id,
        #     username=message.from_user.username)
        success = await add_days(telegram_id=str(user_id),days=DAYS[plan_key]) # количество дней добавленных к подписке
        if success:
            await message.answer(
                f"✅ Оплата прошла успешно!\n"
                f"Подписка активирована.\n\n"
                f"Проверьте Личный кабинет"
            )
            # Очищаем кэш пользователя
            await invalidate_user_cache(str(user_id))
        else:
            await message.answer("❌ Ошибка активации подписки. Обратитесь в поддержку.")

    except Exception as e:
        print(f"Ошибка обработки платежа: {e}")
        await message.answer("❌ Произошла ошибка. Мы уже уведомлены.")