from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from .auth import current_user
from .db import Session, Transaction, Budget, BotReceipt, RecognitionDraft, init_db
from .finance import Entry, serialize, summary
from .planning import router as planning_router, Goal, Subscription, row_dict
from .webhook import router as webhook_router
from .ai_routes import router as ai_router
from .integrations import provider

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield

app = FastAPI(title='Expense Analytics', lifespan=lifespan)
app.include_router(planning_router)
app.include_router(webhook_router)
app.include_router(ai_router)

@app.get('/api/health')
def health():
    return {'status': 'ok'}

@app.get('/api/transactions')
def transactions(user: int = Depends(current_user)):
    with Session() as session:
        return [serialize(row) for row in session.scalars(select(Transaction).where(Transaction.user_id == user).order_by(Transaction.date.desc(), Transaction.id.desc()).limit(1000))]

@app.post('/api/transactions', status_code=201)
def create(entry: Entry, user: int = Depends(current_user)):
    with Session() as session:
        row = Transaction(user_id=user, **entry.model_dump())
        session.add(row)
        session.commit()
        session.refresh(row)
        return serialize(row)

@app.put('/api/transactions/{entry_id}')
def update(entry_id: int, entry: Entry, user: int = Depends(current_user)):
    with Session() as session:
        row = session.get(Transaction, entry_id)
        if not row or row.user_id != user:
            raise HTTPException(404, 'Операция не найдена')
        for key, value in entry.model_dump().items():
            setattr(row, key, value)
        session.commit()
        return serialize(row)

@app.delete('/api/transactions/{entry_id}', status_code=204)
def remove(entry_id: int, user: int = Depends(current_user)):
    with Session() as session:
        row = session.get(Transaction, entry_id)
        if not row or row.user_id != user:
            raise HTTPException(404, 'Операция не найдена')
        session.delete(row)
        session.commit()
    return Response(status_code=204)

@app.get('/api/summary')
def get_summary(month: str = Query(default='', pattern=r'^(\d{4}-\d{2})?$'), user: int = Depends(current_user)):
    with Session() as session:
        try:
            return summary(session, user, month or date.today().strftime('%Y-%m'))
        except ValueError:
            raise HTTPException(422, 'Некорректный месяц')

class BudgetInput(BaseModel):
    amount: int = Field(gt=0, le=100_000_000_000)

@app.put('/api/budget')
def set_budget(body: BudgetInput, user: int = Depends(current_user)):
    with Session() as session:
        session.merge(Budget(user_id=user, amount=body.amount))
        session.commit()
    return body

@app.get('/api/export')
def export(user: int = Depends(current_user)):
    with Session() as session:
        return [serialize(r) for r in session.scalars(select(Transaction).where(Transaction.user_id == user))]

@app.get('/api/export/all')
def export_all(user: int = Depends(current_user)):
    with Session() as session:
        budget = session.get(Budget, user)
        return {'transactions':[serialize(r) for r in session.scalars(select(Transaction).where(Transaction.user_id == user))], 'goals':[row_dict(r) for r in session.scalars(select(Goal).where(Goal.user_id == user))], 'subscriptions':[row_dict(r) for r in session.scalars(select(Subscription).where(Subscription.user_id == user))], 'budget':budget.amount if budget else None}

@app.get('/api/capabilities')
async def capabilities(user: int = Depends(current_user)):
    return await provider.capabilities()

@app.delete('/api/data', status_code=204)
def erase(user: int = Depends(current_user)):
    with Session() as session:
        session.execute(delete(Transaction).where(Transaction.user_id == user))
        session.execute(delete(Budget).where(Budget.user_id == user))
        session.execute(delete(Goal).where(Goal.user_id == user))
        session.execute(delete(Subscription).where(Subscription.user_id == user))
        session.execute(delete(BotReceipt).where(BotReceipt.user_id == user))
        session.execute(delete(RecognitionDraft).where(RecognitionDraft.user_id == user))
        session.commit()
    return Response(status_code=204)

if Path('frontend/dist').exists():
    app.mount('/', StaticFiles(directory='frontend/dist', html=True), name='frontend')
