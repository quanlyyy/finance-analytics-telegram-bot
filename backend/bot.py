import asyncio
import json
import time
import uuid
from datetime import date
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, CallbackQuery, FSInputFile
from .config import BOT_TOKEN, MINI_APP_URL
from .db import init_db, Session, Transaction, BotReceipt, RecognitionDraft
from .planning import Goal, Subscription, row_dict
from .integrations import provider, AIUnavailable
from sqlalchemy import select, delete
from .finance import parse_expense, summary, Entry
from .recognition import preview
from .ai_routes import context_for
from .telegram_client import create_bot
from . import config

dp = Dispatcher()
dp.message.filter(F.chat.type == 'private')

@dp.message(Command('start', 'help'))
@dp.message(F.text.lower().in_({'старт', 'start'}))
async def start(message: Message):
    buttons = []
    if MINI_APP_URL.startswith('https://'):
        buttons.append([InlineKeyboardButton(text='Открыть аналитику', web_app=WebAppInfo(url=MINI_APP_URL))])
    buttons.append([InlineKeyboardButton(text='Поддержать автора', callback_data='support_author')])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    caption = ('Ваш финансовый помощник.\n\nДобавить расход: кофе 250\nДобавить доход: зарплата 80000\n'
               '/report — отчёт за месяц\n/goals — цели\n/payments — запланированные платежи\n\n'
               'В приложении доступны аналитика, цели, платежи и импорт CSV. Суммы в рублях.\n'
               'Пришлите голосовое до 30 секунд или фото чека — предложу операцию для подтверждения.\n'
               '/ask ваш вопрос — локальный ИИ-помощник. Он может ошибаться; проверяйте суммы.')
    banner_url = f'{MINI_APP_URL.rstrip("/")}/start-banner-ru.jpg'
    banner_path = Path(__file__).resolve().parents[1] / 'frontend' / 'dist' / 'start-banner-ru.jpg'
    photo = FSInputFile(banner_path) if config.BOT_MODE == 'polling' and banner_path.is_file() else banner_url
    return message.answer_photo(photo=photo, caption=caption, reply_markup=keyboard)

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
    if message.voice.duration > 30:
        return message.answer('Запишите одно короткое сообщение до 30 секунд: например, «кофе двести рублей».')
    return await recognize_message(message, 'voice', message.voice)

@dp.message(F.photo)
async def photo(message: Message):
    return await recognize_message(message, 'receipt', message.photo[-1])

async def recognize_message(message, kind, media):
    if not media.file_size or media.file_size > 6_000_000:
        return message.answer('Пришлите файл размером до 6 МБ.')
    await message.answer('Распознаю… Это может занять до двух минут. Запись появится только после подтверждения.')
    try:
        content = await message.bot.download(media, timeout=60)
        try:
            data = content.read(6_000_001)
        finally:
            content.close()
        result = preview(await provider.recognize(message.from_user.id, kind, data), kind)
    except AIUnavailable as exc:
        return message.answer(str(exc))
    except Exception:
        return message.answer('Не удалось получить файл. Повторите отправку или добавьте операцию вручную.')
    entry = result['entry']
    if entry['amount'] is None:
        return message.answer('Распознано:\n' + result['text'][:2400] + '\n\nНе удалось однозначно определить сумму. Ничего не сохранено. Отправьте описание и сумму текстом или загрузите файл в разделе «Распознавание» приложения.')
    token = uuid.uuid4().hex
    with Session() as session:
        session.execute(delete(RecognitionDraft).where(RecognitionDraft.expires < int(time.time())))
        session.add(RecognitionDraft(id=token,user_id=message.from_user.id,payload=json.dumps(entry,ensure_ascii=False),expires=int(time.time())+86400))
        session.commit()
    return message.answer(f"Проверьте операцию:\n{entry['note']}\n{entry['amount']/100:,.2f} ₽ · {entry['category']}\nТип: {'доход' if entry['kind']=='income' else 'расход'}\nДата: {entry['date']}\n\nЕсли есть ошибка, отмените и отправьте исправленный текст.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Сохранить',callback_data='recognize:'+token),InlineKeyboardButton(text='Отмена',callback_data='discard:'+token)]]))

@dp.callback_query(F.data.startswith('recognize:') | F.data.startswith('discard:'))
async def confirm_recognition(callback: CallbackQuery):
    action, token = callback.data.split(':',1)
    with Session() as session:
        payload = session.execute(delete(RecognitionDraft).where(RecognitionDraft.id==token,RecognitionDraft.user_id==callback.from_user.id,RecognitionDraft.expires>=int(time.time())).returning(RecognitionDraft.payload)).scalar_one_or_none()
        if payload is None:
            return callback.answer('Черновик уже обработан или истёк.')
        if action=='recognize':
            entry = Entry.model_validate_json(payload)
            session.add(Transaction(user_id=callback.from_user.id,**entry.model_dump()))
        session.commit()
    return callback.answer('Операция сохранена' if action=='recognize' else 'Отменено',show_alert=True)

@dp.message(Command('ask','ai'))
async def ask(message: Message):
    question = message.text.partition(' ')[2].strip()
    if not question or len(question)>600:
        return message.answer('Напишите /ask и вопрос до 600 символов. Например: /ask Как уменьшить расходы?')
    await message.answer('Готовлю ответ локального ИИ… Это может занять до двух минут.')
    try:
        result = await provider.process(message.from_user.id,'chat',question=question,context=context_for(message.from_user.id,date.today().strftime('%Y-%m')))
        return message.answer(result['answer']+'\n\nЛокальный ИИ может ошибаться. Проверяйте выводы по аналитике.')
    except AIUnavailable as exc:
        return message.answer(str(exc))

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
    return message.answer('Пришлите текст «продукты 1500», голосовое до 30 секунд или фото чека. Вопрос помощнику: /ask ваш вопрос.')

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
