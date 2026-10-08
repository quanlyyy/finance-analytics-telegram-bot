import re
from datetime import date as Date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field
from sqlalchemy import select
from .db import Transaction, Budget

class Entry(BaseModel):
    amount: int = Field(gt=0, le=100_000_000_000)
    kind: Literal['expense', 'income'] = 'expense'
    category: str = Field(min_length=1, max_length=80)
    note: str = Field(default='', max_length=300)
    date: Date = Field(default_factory=Date.today)

def serialize(row):
    return {k: getattr(row, k) for k in ['id', 'amount', 'kind', 'category', 'note', 'date']}

def parse_expense(text: str) -> Entry:
    match = re.fullmatch(r'(.+?)\s+(\d+(?:[.,]\d{1,2})?)\s*(?:₽|руб(?:лей|ля)?\.?)?', text.strip(), re.I)
    if not match:
        raise ValueError('Напишите описание и сумму: кофе 250 или зарплата 80000')
    note, value = match.groups()
    category = 'Другое'
    lower_note = note.casefold()
    for name, words in {
        'Продукты': ['продукт', 'магазин', 'молок', 'хлеб', 'сыр', 'мяс', 'овощ', 'фрукт', 'яйц', 'сметан', 'кефир', 'творог', 'круп', 'макарон', 'колбас', 'рыб', 'пекарн'],
        'Развлечения': ['кино', 'фильм', 'аквапарк', 'парк развлеч', 'развлеч', 'театр', 'концерт', 'музе', 'боулинг', 'квест', 'аттракцион', 'зоопарк'],
        'Кафе': ['кофе', 'кафе', 'ресторан', 'доставка', 'обед', 'ужин'],
        'Транспорт': ['такси', 'метро', 'бензин', 'автобус', 'трамвай', 'проезд'],
        'Дом': ['аренда', 'коммунал'],
        'Здоровье': ['аптек', 'врач'],
    }.items():
        if any(word in lower_note for word in words):
            category = name
            break
    income = any(word in lower_note for word in ['зарплата', 'доход', 'аванс'])
    return Entry(amount=int(Decimal(value.replace(',', '.')) * 100), kind='income' if income else 'expense', category='Доход' if income else category, note=note)

def summary(session, user_id: int, month: str):
    start = Date.fromisoformat(month + '-01')
    end = Date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    rows = session.scalars(select(Transaction).where(Transaction.user_id == user_id, Transaction.date >= start, Transaction.date < end)).all()
    income = sum(r.amount for r in rows if r.kind == 'income')
    expense = sum(r.amount for r in rows if r.kind == 'expense')
    categories = {}
    for row in rows:
        if row.kind == 'expense':
            categories[row.category] = categories.get(row.category, 0) + row.amount
    budget = session.get(Budget, user_id)
    tips = []
    if categories:
        top = max(categories, key=categories.get)
        tips.append(f'Наибольшие расходы за выбранный месяц: {top} — {categories[top] / 100:,.2f} ₽.')
    if budget:
        remaining = budget.amount - expense
        tips.append(f'До лимита осталось {remaining / 100:,.2f} ₽.' if remaining >= 0 else f'Лимит превышен на {-remaining / 100:,.2f} ₽.')
    if not rows:
        tips.append('Добавьте первые операции — здесь появится разбор ваших расходов.')
    tips.append('Выводы учитывают только внесённые операции. Остаток за месяц не равен балансу банковских счетов.')
    return dict(income=income, expense=expense, net=income-expense, categories=categories, budget=budget.amount if budget else 0, tips=tips)
