"""Goals, recurring payments, previewed CSV imports and deterministic advice."""
import csv
import io
import calendar
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import String, BigInteger, Date, select, update
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, Session, Transaction
from .auth import current_user
from .finance import Entry, serialize, summary

router = APIRouter(prefix='/api')

class Goal(Base):
    __tablename__ = 'goals'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(100))
    target: Mapped[int] = mapped_column(BigInteger)
    saved: Mapped[int] = mapped_column(BigInteger)
    deadline: Mapped[date] = mapped_column(Date)

class Subscription(Base):
    __tablename__ = 'subscriptions'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(100))
    amount: Mapped[int] = mapped_column(BigInteger)
    due: Mapped[date] = mapped_column(Date)
    category: Mapped[str] = mapped_column(String(80))

class GoalInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    target: int = Field(gt=0, le=100_000_000_000)
    saved: int = Field(ge=0, le=100_000_000_000)
    deadline: date

class SubscriptionInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    amount: int = Field(gt=0, le=100_000_000_000)
    due: date
    category: str = Field(default='Подписки', min_length=1, max_length=80)

def owned(session, model, key, user):
    row = session.get(model, key)
    if row is None or row.user_id != user:
        raise HTTPException(404, 'Запись не найдена')
    return row

def row_dict(row):
    return {c.name:getattr(row,c.name) for c in row.__table__.columns if c.name != 'user_id'}

@router.get('/planning')
def planning(user: int = Depends(current_user)):
    with Session() as session:
        return {name:[row_dict(r) for r in session.scalars(select(model).where(model.user_id == user))] for name,model in [('goals',Goal),('subscriptions',Subscription)]}

@router.post('/goals', status_code=201)
def add_goal(body: GoalInput, user: int = Depends(current_user)):
    with Session() as session:
        row=Goal(user_id=user,**body.model_dump());session.add(row);session.commit()
        return row_dict(row)

@router.put('/goals/{key}')
def edit_goal(key:int,body:GoalInput,user:int=Depends(current_user)):
    with Session() as session:
        row=owned(session,Goal,key,user)
        for k,v in body.model_dump().items():setattr(row,k,v)
        session.commit();return row_dict(row)

@router.delete('/goals/{key}')
def delete_goal(key:int,user:int=Depends(current_user)):
    with Session() as session:
        session.delete(owned(session,Goal,key,user));session.commit()
    return {'deleted':True}

@router.post('/subscriptions', status_code=201)
def add_subscription(body:SubscriptionInput,user:int=Depends(current_user)):
    with Session() as session:
        row=Subscription(user_id=user,**body.model_dump());session.add(row);session.commit()
        return row_dict(row)

@router.put('/subscriptions/{key}')
def edit_subscription(key:int,body:SubscriptionInput,user:int=Depends(current_user)):
    with Session() as session:
        row=owned(session,Subscription,key,user)
        for k,v in body.model_dump().items():setattr(row,k,v)
        session.commit();return row_dict(row)

@router.delete('/subscriptions/{key}')
def delete_subscription(key:int,user:int=Depends(current_user)):
    with Session() as session:
        session.delete(owned(session,Subscription,key,user));session.commit()
    return {'deleted':True}

class PaymentInput(BaseModel):
    expected_due:date

@router.post('/subscriptions/{key}/pay')
def pay_subscription(key:int,body:PaymentInput,user:int=Depends(current_user)):
    with Session() as session:
        row=owned(session,Subscription,key,user)
        year=row.due.year+(row.due.month==12);month=row.due.month%12+1
        next_due=date(year,month,min(row.due.day,calendar.monthrange(year,month)[1]))
        changed=session.execute(update(Subscription).where(Subscription.id==key,Subscription.user_id==user,Subscription.due==body.expected_due).values(due=next_due))
        if changed.rowcount!=1:raise HTTPException(409,'Этот платёж уже отмечен. Обновите страницу.')
        session.add(Transaction(user_id=user,amount=row.amount,kind='expense',category=row.category,note=row.name,date=date.today()))
        session.commit()
    return {'next_due':next_due}

class CSVInput(BaseModel):
    text:str=Field(max_length=500000)

def parse_csv(text):
    text=text.lstrip('\ufeff')
    delimiter=';' if ';' in text.partition('\n')[0] else ','
    reader=csv.DictReader(io.StringIO(text),delimiter=delimiter)
    if not reader.fieldnames or not {'date','amount','category'}.issubset(reader.fieldnames):
        raise ValueError('Нужны столбцы date,amount,category,note. Дата YYYY-MM-DD; расход отрицательный, доход положительный.')
    result=[]
    for index,row in enumerate(reader,2):
        if len(result)>=1000:raise ValueError('Не более 1000 строк за один импорт')
        try:
            value=Decimal(row['amount'].replace(' ','').replace(',','.'))
            if not value.is_finite() or value == 0 or value*100 != (value*100).to_integral_value():raise ValueError()
            result.append(Entry(amount=int(abs(value)*100),kind='expense' if value<0 else 'income',date=row['date'],category=row['category'],note=row.get('note') or ''))
        except (ValueError,InvalidOperation,AttributeError):
            raise ValueError(f'Ошибка в строке {index}: проверьте дату, сумму и категорию')
    return result

def fingerprint(entry):
    return (entry.date,entry.amount,entry.kind,entry.category,entry.note)

def duplicates(session,user,entries):
    known={fingerprint(r) for r in session.scalars(select(Transaction).where(Transaction.user_id==user))}
    output=[]
    for entry in entries:
        key=fingerprint(entry);output.append(key in known);known.add(key)
    return output

@router.post('/import/preview')
def preview(body:CSVInput,user:int=Depends(current_user)):
    try:entries=parse_csv(body.text)
    except ValueError as e:raise HTTPException(422,str(e))
    with Session() as session:
        flags=duplicates(session,user,entries)
    return [{'entry':entry.model_dump(),'duplicate':duplicate} for entry,duplicate in zip(entries,flags)]

class ImportInput(BaseModel):
    entries:list[Entry]=Field(max_length=1000)

@router.post('/import/confirm')
def confirm_import(body:ImportInput,user:int=Depends(current_user)):
    with Session() as session:
        flags=duplicates(session,user,body.entries)
        for entry,duplicate in zip(body.entries,flags):
            if not duplicate:session.add(Transaction(user_id=user,**entry.model_dump()))
        session.commit()
    return {'imported':len(flags)-sum(flags),'skipped':sum(flags)}

@router.get('/comparison')
def comparison(month:str,user:int=Depends(current_user)):
    try:
        start=date.fromisoformat(month+'-01');previous=(start-timedelta(days=1)).strftime('%Y-%m')
        with Session() as session:
            current=summary(session,user,month);before=summary(session,user,previous)
        return {'current':current,'previous':before,'previous_month':previous,'change':current['expense']-before['expense']}
    except ValueError:raise HTTPException(422,'Некорректный месяц')

class PurchaseInput(BaseModel):
    amount:int=Field(gt=0,le=100_000_000_000)

@router.post('/advisor/purchase')
def purchase(body:PurchaseInput,user:int=Depends(current_user)):
    today=date.today()
    with Session() as session:
        data=summary(session,user,today.strftime('%Y-%m'))
        upcoming=session.scalars(select(Subscription).where(Subscription.user_id==user,Subscription.due>=today,Subscription.due<=date(today.year,today.month,calendar.monthrange(today.year,today.month)[1]))).all()
        reserved=sum(r.amount for r in upcoming)
    if not data['budget']:return {'answer':'Сначала задайте месячный лимит. Без него нельзя оценить покупку относительно бюджета.'}
    remaining=data['budget']-data['expense']-reserved-body.amount
    return {'answer':f'После покупки и запланированных платежей останется {remaining/100:,.2f} ₽ от месячного лимита. '+('Покупка укладывается в лимит.' if remaining>=0 else 'Покупка превышает доступный лимит.')+' Это оценка бюджета, а не проверка средств на счетах; накопления на цели не вычтены.'}
