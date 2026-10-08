"""Read-only production checks. Never logs tokens, auth headers, or user data."""
import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode
import httpx
from backend.telegram_client import create_bot
from backend.config import BOT_TOKEN, MINI_APP_URL

async def main():
    data={'auth_date':str(int(time.time())),'user':json.dumps({'id':4000000000000001,'first_name':'Deployment check'})}
    secret=hmac.new(b'WebAppData',BOT_TOKEN.encode(),hashlib.sha256).digest()
    data['hash']=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(data.items())).encode(),hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(base_url=MINI_APP_URL,timeout=20) as client:
        for path,headers,expected in [('/api/health',{},200),('/api/transactions',{},401),('/api/transactions',{'Authorization':'Bearer local-demo'},401),('/api/transactions',{'Authorization':'tma '+urlencode(data)},200),('/',{},200)]:
            response=await client.get(path,headers=headers)
            assert response.status_code==expected,f'{path}: unexpected HTTP {response.status_code}'
            print(path, 'OK',response.status_code)
        response=await client.post('/api/telegram/webhook',json={})
        assert response.status_code==403
        print('Webhook rejects unauthenticated requests: OK')
    async with create_bot() as bot:
        info=await bot.get_webhook_info()
        print('Webhook URL:',info.url)
        print('Webhook IP:',info.ip_address)
        print('Last error date:',info.last_error_date)
        print('Pending updates:',info.pending_update_count)
        print('Webhook error:',info.last_error_message or 'none')

if __name__=='__main__':asyncio.run(main())
