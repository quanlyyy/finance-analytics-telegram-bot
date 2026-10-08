import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl
from fastapi import Header, HTTPException
from . import config

def validate_init_data(raw: str, token: str, now: float | None = None) -> int:
    pairs = parse_qsl(raw, keep_blank_values=True)
    data = dict(pairs)
    if len(data) != len(pairs):
        raise ValueError('Duplicate fields')
    signature = data.pop('hash', '')
    check = '\n'.join(f'{k}={v}' for k, v in sorted(data.items()))
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not token or not hmac.compare_digest(expected, signature):
        raise ValueError('Invalid signature')
    age = (time.time() if now is None else now) - int(data['auth_date'])
    if age < -30 or age > 86400:
        raise ValueError('Expired session')
    user_id = json.loads(data['user'])['id']
    if type(user_id) is not int or user_id <= 0:
        raise ValueError('Invalid user')
    return user_id

def current_user(authorization: str = Header(default='')) -> int:
    if config.DEV_AUTH and authorization == 'Bearer local-demo':
        return 1
    try:
        if not authorization.startswith('tma '):
            raise ValueError('Missing Telegram session')
        return validate_init_data(authorization[4:], config.BOT_TOKEN)
    except (ValueError, KeyError, TypeError):
        raise HTTPException(401, 'Откройте приложение заново через Telegram')
