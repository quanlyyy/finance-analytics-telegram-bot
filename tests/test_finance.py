import hashlib
import hmac
import json
from urllib.parse import urlencode
from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from backend.auth import validate_init_data, current_user
from backend.finance import parse_expense
from backend.db import Base
import backend.main as api

def signed(user=123, timestamp=1000):
    data = {'auth_date': str(timestamp), 'user': json.dumps({'id': user})}
    secret = hmac.new(b'WebAppData', b'test-token', hashlib.sha256).digest()
    data['hash'] = hmac.new(secret, '\n'.join(f'{k}={v}' for k,v in sorted(data.items())).encode(), hashlib.sha256).hexdigest()
    return urlencode(data)

def test_auth():
    assert validate_init_data(signed(), 'test-token', now=1001) == 123
    for raw, token, now in [(signed(), 'wrong',1001),(signed(), 'test-token',90000),(signed(), 'test-token',900),(signed()+'&auth_date=1000','test-token',1001)]:
        with pytest.raises(ValueError):
            validate_init_data(raw, token, now)

def test_parser_money():
    assert parse_expense('кофе 250,35').amount == 25035
    assert parse_expense('зарплата 80000').kind == 'income'
    assert parse_expense('кофе 250').category == 'Кафе'
    with pytest.raises(ValueError):
        parse_expense('кофе -250')
    with pytest.raises(ValueError):
        parse_expense('кофе 0')

@pytest.fixture
def client(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(api, 'Session', sessionmaker(engine))
    monkeypatch.setattr(api, 'init_db', lambda: None)
    api.app.dependency_overrides[current_user] = lambda:123
    with TestClient(api.app) as client:
        yield client
    api.app.dependency_overrides.clear()
    engine.dispose()

def test_crud_summary_and_ownership(client):
    entry = {'amount':12535,'category':'Кафе','date':'2026-10-08','kind':'expense'}
    response = client.post('/api/transactions',json=entry)
    assert response.status_code == 201
    entry_id=response.json()['id']
    client.post('/api/transactions',json={**entry,'kind':'income','amount':100000})
    data=client.get('/api/summary?month=2026-10').json()
    assert data['expense']==12535 and data['net']==87465
    assert client.get('/api/summary?month=2026-09').json()['expense']==0
    assert client.get('/api/summary?month=2026-13').status_code==422
    assert client.post('/api/transactions',json={**entry,'amount':0}).status_code==422
    api.app.dependency_overrides[current_user]=lambda:456
    assert client.get('/api/transactions').json()==[]
    assert client.delete(f'/api/transactions/{entry_id}').status_code==404
    assert client.put(f'/api/transactions/{entry_id}',json=entry).status_code==404
    assert client.get('/api/export').json()==[]
    client.delete('/api/data')
    api.app.dependency_overrides[current_user]=lambda:123
    assert len(client.get('/api/transactions').json())==2
    assert client.put(f'/api/transactions/{entry_id}',json={**entry,'amount':20000}).status_code==200
    assert client.get('/api/summary?month=2026-10').json()['expense']==20000
    assert client.put('/api/budget',json={'amount':30000}).status_code==200
    assert client.get('/api/summary?month=2026-10').json()['budget']==30000
    assert client.delete('/api/data').status_code==204
    assert client.get('/api/transactions').json()==[]
    assert client.get('/api/summary').json()['budget']==0

def test_no_auth_rejected(client):
    api.app.dependency_overrides.clear()
    assert client.get('/api/transactions').status_code==401
