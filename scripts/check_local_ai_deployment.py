"""Read-only deployment check; uses a reserved synthetic user, sends no messages."""
import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode
from pathlib import Path
import httpx
from backend import config
from backend.telegram_client import create_bot

async def main():
    data={'auth_date':str(int(time.time())),'user':json.dumps({'id':9000000000000001})}
    secret=hmac.new(b'WebAppData',config.BOT_TOKEN.encode(),hashlib.sha256).digest()
    data['hash']=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(data.items())).encode(),hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(base_url='http://localhost:8000',timeout=180) as client:
        assert (await client.get('/api/health')).status_code==200
        assert (await client.post('/api/ai/chat',json={'question':'Привет'})).status_code==401
        headers={'Authorization':'tma '+urlencode(data)}
        response=await client.get('/api/capabilities',headers=headers)
        response.raise_for_status()
        print('capabilities',response.json(),flush=True)
        assert all(response.json()[key] for key in ('voice','receipt','ai_chat'))
        response=await client.post('/api/ai/chat',json={'question':'У меня пока нет операций. С чего начать вести бюджет?'},headers=headers)
        response.raise_for_status()
        assert response.json()['answer'].strip()
        print('authenticated chat OK; model:',response.json().get('model'),flush=True)
    assert config.BOT_MODE=='polling'
    assert Path('frontend/dist/start-banner-ru.jpg').is_file()
    async with create_bot() as bot:
        me=await bot.get_me();webhook=await bot.get_webhook_info()
        assert not webhook.url
        print('Telegram connectivity OK:',me.username,'polling mode, banner present',flush=True)

if __name__=='__main__':asyncio.run(main())
