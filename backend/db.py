from pathlib import Path
from datetime import date
from sqlalchemy import BigInteger, Integer, String, Date, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import DATABASE_URL

Path('data').mkdir(exist_ok=True)
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {})
Session = sessionmaker(engine)

class Base(DeclarativeBase):
    pass

class Transaction(Base):
    __tablename__ = 'transactions'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(10))
    category: Mapped[str] = mapped_column(String(80))
    note: Mapped[str] = mapped_column(String(300))
    date: Mapped[date] = mapped_column(Date)

class Budget(Base):
    __tablename__ = 'budgets'
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    amount: Mapped[int] = mapped_column(BigInteger)

class BotReceipt(Base):
    __tablename__ = 'bot_receipts'
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(BigInteger)

def init_db():
    Base.metadata.create_all(engine)
