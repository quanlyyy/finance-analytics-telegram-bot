import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from backend.auth import current_user
from backend.db import Base
import backend.main as api
import backend.planning as planning

@pytest.fixture
def client(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session=sessionmaker(engine)
    monkeypatch.setattr(api,'Session',session);monkeypatch.setattr(planning,'Session',session)
    monkeypatch.setattr(api,'init_db',lambda:None)
    api.app.dependency_overrides[current_user]=lambda:123
    with TestClient(api.app) as c:yield c
    api.app.dependency_overrides.clear();engine.dispose()

def test_goals_and_subscriptions_isolated(client):
    goal={'name':'Отпуск','target':500000,'saved':10000,'deadline':'2027-01-01'}
    key=client.post('/api/goals',json=goal).json()['id']
    payment={'name':'Интернет','amount':10000,'due':'2026-10-15'}
    subkey=client.post('/api/subscriptions',json=payment).json()['id']
    assert len(client.get('/api/planning').json()['goals'])==1
    api.app.dependency_overrides[current_user]=lambda:456
    assert client.get('/api/planning').json()=={'goals':[],'subscriptions':[]}
    assert client.put(f'/api/goals/{key}',json=goal).status_code==404
    assert client.delete(f'/api/subscriptions/{subkey}').status_code==404
    api.app.dependency_overrides[current_user]=lambda:123
    assert client.put(f'/api/goals/{key}',json={**goal,'saved':50000}).json()['saved']==50000
    assert client.get('/api/export/all').json()['goals'][0]['saved']==50000
    client.delete('/api/data')
    assert client.get('/api/planning').json()=={'goals':[],'subscriptions':[]}

def test_csv_preview_confirm_and_duplicates(client):
    text='date,amount,category,note\n2026-10-08,-250.35,Кафе,Кофе\n2026-10-08,80000,Доход,Зарплата'
    preview=client.post('/api/import/preview',json={'text':text})
    assert preview.status_code==200
    rows=preview.json()
    assert rows[0]['entry']['amount']==25035
    assert client.get('/api/transactions').json()==[]
    body={'entries':[r['entry'] for r in rows]}
    assert client.post('/api/import/confirm',json=body).json()=={'imported':2,'skipped':0}
    assert client.post('/api/import/confirm',json=body).json()=={'imported':0,'skipped':2}
    assert all(r['duplicate'] for r in client.post('/api/import/preview',json={'text':text}).json())
    assert client.post('/api/import/preview',json={'text':text.replace('-250.35','NaN')}).status_code==422
    assert client.post('/api/import/preview',json={'text':text.replace('-250.35','0.001')}).status_code==422
    assert client.post('/api/import/preview',json={'text':'a,b\n1,2'}).status_code==422

def test_purchase_requires_budget_and_comparison(client):
    assert 'Сначала' in client.post('/api/advisor/purchase',json={'amount':5000}).json()['answer']
    client.put('/api/budget',json={'amount':100000})
    assert '950.00' in client.post('/api/advisor/purchase',json={'amount':5000}).json()['answer']
    data=client.get('/api/comparison?month=2026-01').json()
    assert data['previous_month']=='2025-12'
    assert client.get('/api/comparison?month=bad').status_code==422

def test_payment_confirm_once(client):
    key=client.post('/api/subscriptions',json={'name':'Тест','amount':10000,'due':'2026-01-31'}).json()['id']
    body={'expected_due':'2026-01-31'}
    assert client.post(f'/api/subscriptions/{key}/pay',json=body).json()['next_due']=='2026-02-28'
    assert client.post(f'/api/subscriptions/{key}/pay',json=body).status_code==409
    assert len(client.get('/api/transactions').json())==1
