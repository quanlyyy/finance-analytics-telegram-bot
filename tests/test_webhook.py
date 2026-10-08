import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.db import Base,Transaction
from backend import config
import backend.main as api
import backend.bot as bot

@pytest.fixture
def client(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions=sessionmaker(engine)
    monkeypatch.setattr(api,'Session',sessions);monkeypatch.setattr(bot,'Session',sessions)
    monkeypatch.setattr(api,'init_db',lambda:None)
    monkeypatch.setattr(config,'WEBHOOK_SECRET','test-webhook-secret')
    monkeypatch.setattr(config,'BOT_MODE','webhook')
    monkeypatch.setattr(bot,'MINI_APP_URL','https://example.com')
    monkeypatch.setattr(config,'BOT_TOKEN','123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789')
    with TestClient(api.app) as c:yield c,sessions
    engine.dispose()

def event(text='кофе 250'):
    return {'update_id':1,'message':{'message_id':10,'date':1700000000,'chat':{'id':123,'type':'private'},'from':{'id':123,'is_bot':False,'first_name':'Test'},'text':text}}

def test_webhook_secret_and_inline_reply(client):
    c,sessions=client
    assert c.post('/api/telegram/webhook',json=event()).status_code==403
    headers={'X-Telegram-Bot-Api-Secret-Token':'test-webhook-secret'}
    response=c.post('/api/telegram/webhook',json=event(),headers=headers)
    assert response.status_code==200
    data=response.json()
    assert data['method']=='sendMessage' and data['chat_id']==123
    assert data['reply_markup']['inline_keyboard'][0][0]['callback_data'].startswith('undo:')
    assert c.post('/api/telegram/webhook',json=event(),headers=headers).status_code==200
    with sessions() as session:
        assert len(session.scalars(select(Transaction)).all())==1
    assert c.post('/api/telegram/webhook',json={},headers=headers).status_code==422

def test_webhook_ignores_group(client):
    c,sessions=client
    data=event();data['message']['chat']['type']='group'
    assert c.post('/api/telegram/webhook',json=data,headers={'X-Telegram-Bot-Api-Secret-Token':'test-webhook-secret'}).json()=={}
    with sessions() as session:assert not session.scalars(select(Transaction)).all()

@pytest.mark.parametrize('text',['/start','/start app','старт','Старт','start'])
def test_start_reply(client,text):
    c,sessions=client
    response=c.post('/api/telegram/webhook',json=event(text),headers={'X-Telegram-Bot-Api-Secret-Token':'test-webhook-secret'})
    assert response.status_code==200
    data=response.json()
    assert data['method']=='sendPhoto'
    assert 'Ваш финансовый помощник' in data['caption']
    assert data['reply_markup']['inline_keyboard'][1][0]['callback_data']=='support_author'
    assert data['reply_markup']['inline_keyboard'][0][0]['web_app']['url']=='https://example.com'
    with sessions() as session:assert not session.scalars(select(Transaction)).all()
