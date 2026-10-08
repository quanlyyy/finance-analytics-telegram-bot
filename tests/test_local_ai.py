import asyncio
import json
import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from aiogram.types import CallbackQuery,User
from backend.db import Base,Transaction,RecognitionDraft
from backend.recognition import preview
from backend.auth import current_user
import backend.main as api
import backend.ai_routes as routes
import backend.bot as bot

@pytest.mark.parametrize('text,kind,amount,category',[
 ('молоко сто двадцать рублей','voice',12000,'Продукты'),
 ('кино 350 рублей 50 копеек','voice',35050,'Развлечения'),
 ('аквапарк две тысячи пятьсот рублей','voice',250000,'Развлечения'),
 ('кофе 250,50','voice',25050,'Кафе'),
 ('кофе 250 и кино 500','voice',None,'Развлечения'),
 ('МОЛОКО\nИТОГ: 123,45\nНАЛИЧНЫМИ 200\nСДАЧА 76.55','receipt',12345,'Продукты'),
 ('ИТОГО 100.00\nК ОПЛАТЕ 150.00','receipt',None,'Другое'),
 ('Молоко 100\nСДАЧА 50','receipt',None,'Продукты'),
])
def test_preview(text,kind,amount,category):
    entry=preview(text,kind)['entry']
    assert entry['amount']==amount
    assert entry['category']==category

@pytest.fixture
def isolated(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions=sessionmaker(engine)
    for module in (api,routes,bot):monkeypatch.setattr(module,'Session',sessions)
    monkeypatch.setattr(api,'init_db',lambda:None)
    yield sessions
    api.app.dependency_overrides.clear()
    engine.dispose()

def test_preview_auth_and_no_automatic_write(isolated,monkeypatch):
    async def recognize(user,kind,data):
        assert user==123 and data==b'test'
        return 'молоко сто рублей'
    monkeypatch.setattr(routes.provider,'recognize',recognize)
    with TestClient(api.app) as client:
        assert client.post('/api/recognition/preview',json={'kind':'voice','payload':'dGVzdA=='}).status_code==401
        api.app.dependency_overrides[current_user]=lambda:123
        assert client.post('/api/recognition/preview',json={'kind':'voice','payload':'!'}).status_code==422
        response=client.post('/api/recognition/preview',json={'kind':'voice','payload':'dGVzdA=='})
        assert response.status_code==200 and response.json()['entry']['amount']==10000
    with isolated() as s:assert not s.scalars(select(Transaction)).all()

def test_chat_uses_only_authenticated_summary(isolated,monkeypatch):
    with isolated() as s:
        for user,amount in [(123,10000),(999,900000)]:
            s.add(Transaction(user_id=user,amount=amount,kind='expense',category='Продукты',note='private',date=__import__('datetime').date(2026,10,1)))
        s.commit()
    async def process(user,kind,**kwargs):
        assert user==123 and kwargs['context']['expense']==100
        assert 'private' not in json.dumps(kwargs)
        return {'answer':'test'}
    monkeypatch.setattr(routes.provider,'process',process)
    api.app.dependency_overrides[current_user]=lambda:123
    with TestClient(api.app) as client:
        assert client.post('/api/ai/chat',json={'question':'Совет','month':'2026-10','context':{'expense':0},'user_id':999}).json()['answer']=='test'
        assert client.post('/api/ai/chat',json={'question':'Совет','month':'2026-99'}).status_code==422

def test_bot_confirmation_ownership_and_replay(isolated):
    entry=preview('молоко сто рублей','voice')['entry']
    with isolated() as s:
        s.add(RecognitionDraft(id='draft',user_id=123,payload=json.dumps(entry),expires=int(time.time())+60));s.commit()
    def callback(user):return CallbackQuery(id='test',from_user=User(id=user,is_bot=False,first_name='Test'),chat_instance='test',data='recognize:draft')
    asyncio.run(bot.confirm_recognition(callback(999)))
    with isolated() as s:assert not s.scalars(select(Transaction)).all()
    asyncio.run(bot.confirm_recognition(callback(123)))
    asyncio.run(bot.confirm_recognition(callback(123)))
    with isolated() as s:
        rows=s.scalars(select(Transaction)).all()
        assert len(rows)==1 and rows[0].user_id==123 and rows[0].amount==10000
