import asyncio
from datetime import date
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, CallbackQuery
from .config import BOT_TOKEN, MINI_APP_URL
from .db import init_db, Session, Transaction, BotReceipt
from .planning import Goal, Subscription, row_dict
from .integrations import provider, AIUnavailable
from sqlalchemy import select
from .finance import parse_expense, summary
from .telegram_client import create_bot
from . import config

dp = Dispatcher()
dp.message.filter(F.chat.type == 'private')

@dp.message(Command('start', 'help'))
@dp.message(F.text.lower().in_({'старт', 'start'}))
async def start(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Открыть аналитику', web_app=WebAppInfo(url=MINI_APP_URL))], [InlineKeyboardButton(text='Прямая ссылка на приложение', url='https://t.me/finance_analyticsmain_bot/financeapp')], [InlineKeyboardButton(text='Поддержать автора', callback_data='support_author')]]) if MINI_APP_URL.startswith('https://') else None
    return message.answer('Ваш финансовый помощник.\n\nДобавить расход: кофе 250\nДобавить доход: зарплата 80000\n/report — отчёт за месяц\n/goals — цели\n/payments — запланированные платежи\n\nВ приложении доступны аналитика, цели, платежи и импорт CSV. Суммы в рублях. Голос, чеки и ИИ временно отключены до настройки провайдера.', reply_markup=keyboard)

@dp.message(Command('goals'))
async def goals(message: Message):
    with Session() as session:
        rows=session.scalars(select(Goal).where(Goal.user_id==message.from_user.id)).all()
        text='\n'.join(f'{r.name}: {r.saved/100:,.2f} / {r.target/100:,.2f} ₽' for r in rows)
    return message.answer((text or 'Целей пока нет. Добавьте первую в мини-приложении.')[:4000])

@dp.message(Command('payments'))
async def payments(message: Message):
    with Session() as session:
        rows=session.scalars(select(Subscription).where(Subscription.user_id==message.from_user.id).order_by(Subscription.due)).all()
        text='\n'.join(f'{r.due}: {r.name} — {r.amount/100:,.2f} ₽' for r in rows)
    return message.answer((text or 'Запланированных платежей пока нет.')[:4000])

@dp.message(F.voice)
async def voice(message: Message):
    return message.answer('Распознавание голоса пока не подключено. Отправьте расход текстом: кофе 250.')

@dp.message(F.photo)
async def photo(message: Message):
    return message.answer('Распознавание чеков пока не подключено. Добавьте сумму вручную.')

@dp.message(Command('report'))
async def report(message: Message):
    with Session() as session:
        data = summary(session, message.from_user.id, date.today().strftime('%Y-%m'))
    return message.answer(f"За текущий месяц\nДоходы: {data['income']/100:,.2f} ₽\nРасходы: {data['expense']/100:,.2f} ₽\n\n" + '\n'.join(data['tips']))

@dp.callback_query(F.data.startswith('undo:'))
async def undo(callback: CallbackQuery):
    with Session() as session:
        row = session.get(Transaction, int(callback.data.split(':')[1]))
        if row and row.user_id == callback.from_user.id:
            session.delete(row)
            session.commit()
    return callback.answer('Операция отменена')

@dp.callback_query(F.data == 'support_author')
async def support_author(callback: CallbackQuery):
    return callback.answer()

@dp.message(F.text)
async def entry(message: Message):
    try:
        parsed = parse_expense(message.text)
    except ValueError as exc:
        return message.answer(str(exc))
    with Session() as session:
        receipt = session.get(BotReceipt, (message.from_user.id, message.message_id))
        if receipt:
            return message.answer('Эта операция уже обработана. Проверьте историю в мини-приложении.')
        row = Transaction(user_id=message.from_user.id, **parsed.model_dump())
        session.add(row)
        session.flush()
        session.add(BotReceipt(user_id=message.from_user.id, message_id=message.message_id, transaction_id=row.id))
        session.commit()
        entry_id = row.id
    return message.answer(f"Записано: {parsed.note} — {parsed.amount/100:,.2f} ₽\nКатегория: {parsed.category}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Отменить', callback_data=f'undo:{entry_id}')]]))

@dp.message()
async def unsupported(message: Message):
    return message.answer('Пока поддерживается текст: например, продукты 1500. Обработка файлов и голоса ещё не подключена.')

async def main():
    if config.BOT_MODE != 'polling':
        raise RuntimeError('Set BOT_MODE=polling explicitly before starting polling')
    if not BOT_TOKEN:
        raise RuntimeError('Укажите BOT_TOKEN в .env')
    init_db()
    async with create_bot() as bot:
        await bot.get_me()
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
