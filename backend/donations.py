"""Voluntary author support, separate from users' financial transactions."""
from uuid import uuid4

from aiogram.methods import SendInvoice, SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import select

from .db import Donation, Session

DONATEPAY_URL = 'https://donatepay.ru/don/1537607'
STAR_AMOUNTS = (25, 50, 100, 250, 500)
MAX_STARS = 10000
PREFIX = 'author-support:'


def support_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='💙 Поддержать через DonatePay', url=DONATEPAY_URL)],
        [InlineKeyboardButton(text=f'⭐ {amount}', callback_data=f'donate_stars:{amount}') for amount in STAR_AMOUNTS[:3]],
        [InlineKeyboardButton(text=f'⭐ {amount}', callback_data=f'donate_stars:{amount}') for amount in STAR_AMOUNTS[3:]],
        [InlineKeyboardButton(text='📋 История донатов', callback_data='donation_history:0')],
    ])


def support_text():
    return ('💙 Поддержать автора\n\n'
            'Если финансовый помощник вам полезен, вы можете поддержать его развитие. '
            'Выберите DonatePay или сумму в звёздах Telegram.\n\n'
            'Это добровольная поддержка: она не открывает дополнительные функции. '
            'Перед оплатой Telegram покажет сумму и попросит подтверждение.\n\n'
            f'Своя сумма: /donate 150 (от 1 до {MAX_STARS} ⭐).\n'
            'История донатов: /donations.')


def invoice(user_id: int, amount: int):
    donation_id = uuid4().hex
    with Session() as session:
        session.add(Donation(id=donation_id, user_id=user_id, stars=amount))
        session.commit()
    return SendInvoice(
        chat_id=user_id,
        title='Поддержка автора',
        description='Добровольный донат на развитие финансового помощника. Дополнительные функции не предоставляются. История донатов: /donations.',
        payload=PREFIX + donation_id,
        currency='XTR',
        prices=[LabeledPrice(label='Поддержка автора', amount=amount)],
        provider_token='',
        start_parameter='support',
    )


async def donate_command(message: Message):
    parts = (message.text or '').split()
    if len(parts) == 1:
        return message.answer(support_text(), reply_markup=support_keyboard())
    if len(parts) != 2 or not parts[1].isascii() or not parts[1].isdigit() or not 1 <= int(parts[1]) <= MAX_STARS:
        return message.answer(f'Укажите целое число от 1 до {MAX_STARS}: например, /donate 150.')
    return invoice(message.from_user.id, int(parts[1]))


async def support_author(callback: CallbackQuery):
    await callback.answer()
    return SendMessage(chat_id=callback.from_user.id, text=support_text(), reply_markup=support_keyboard())


async def donate_stars(callback: CallbackQuery):
    raw = (callback.data or '').removeprefix('donate_stars:')
    if not raw.isdigit() or int(raw) not in STAR_AMOUNTS or not callback.message or callback.message.chat.type != 'private':
        return await callback.answer('Выберите сумму через /donate.', show_alert=True)
    await callback.answer()
    # Callback messages are authored by the bot; use the callback sender instead.
    return invoice(callback.from_user.id, int(raw))


def matches(row, user_id, currency, amount):
    return row is not None and row.user_id == user_id and currency == 'XTR' and row.stars == amount


async def pre_checkout(query: PreCheckoutQuery):
    valid = False
    if query.invoice_payload.startswith(PREFIX):
        with Session() as session:
            row = session.get(Donation, query.invoice_payload[len(PREFIX):])
            valid = matches(row, query.from_user.id, query.currency, query.total_amount) and row.status == 'pending'
    return query.answer(ok=valid, error_message=None if valid else 'Не удалось проверить платёж. Создайте новый через /donate.')


async def successful_payment(message: Message):
    payment = message.successful_payment
    with Session() as session:
        row = session.get(Donation, payment.invoice_payload[len(PREFIX):]) if payment.invoice_payload.startswith(PREFIX) else None
        if not matches(row, message.from_user.id, payment.currency, payment.total_amount):
            return message.answer('Получено уведомление о платеже, но его данные не совпали со счётом. Проверьте квитанцию Telegram и историю: /donations.')
        if row.status in ('paid', 'refunded'):
            return message.answer('Этот платёж уже обработан. История донатов: /donations.')
        row.charge_id = payment.telegram_payment_charge_id
        row.status = 'paid'
        session.commit()
    return message.answer(f'Спасибо за донат! 💙 Получено {payment.total_amount} ⭐.\nИстория донатов: /donations.')


def donation_history_response(user_id: int, offset: int = 0):
    with Session() as session:
        rows = session.scalars(select(Donation).where(
            Donation.user_id == user_id, Donation.status.in_(('paid', 'refunded'))
        ).order_by(Donation.created_at.desc(), Donation.id.desc()).offset(offset).limit(11)).all()
        history = '\n\n'.join(
            f'{row.created_at:%d.%m.%Y} · {row.stars} ⭐ · '
            f'{"возвращён" if row.status == "refunded" else "оплачен"}\nНомер платежа: {row.id}'
            for row in rows[:10]
        )
    buttons = []
    navigation = []
    if offset:
        navigation.append(InlineKeyboardButton(text='← Назад', callback_data=f'donation_history:{max(0, offset - 10)}'))
    if len(rows) > 10:
        navigation.append(InlineKeyboardButton(text='Далее →', callback_data=f'donation_history:{offset + 10}'))
    if navigation:
        buttons.append(navigation)
    buttons.append([InlineKeyboardButton(text='💙 Сделать донат', callback_data='support_author')])
    buttons.append([InlineKeyboardButton(text='Открыть DonatePay', url=DONATEPAY_URL)])
    return SendMessage(
        chat_id=user_id,
        text=('📋 История донатов\n\n'
              + (history if history else 'На этой странице подтверждённых донатов в звёздах нет.')
              + '\n\nЗдесь учитываются донаты в Telegram Stars. Операции DonatePay доступны на стороне DonatePay.'),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


async def pay_support(message: Message):
    # Compatibility with the previous command; only shows the payment history.
    return donation_history_response(message.from_user.id)


async def donation_history(callback: CallbackQuery):
    raw = (callback.data or '').removeprefix('donation_history:')
    if not raw.isdigit() or not 0 <= int(raw) <= 1000000:
        return await callback.answer('Откройте историю через /donations.', show_alert=True)
    await callback.answer()
    return donation_history_response(callback.from_user.id, int(raw))


async def legacy_payment_support(callback: CallbackQuery):
    # Old messages still contain refund buttons. They must not trigger a refund.
    await callback.answer()
    return donation_history_response(callback.from_user.id)


async def refunded_payment(message: Message):
    payment = message.refunded_payment
    with Session() as session:
        row = session.scalar(select(Donation).where(Donation.charge_id == payment.telegram_payment_charge_id))
        if matches(row, message.from_user.id, payment.currency, payment.total_amount):
            row.status = 'refunded'
            session.commit()
    return message.answer('Telegram обновил статус платежа. История: /donations.')
