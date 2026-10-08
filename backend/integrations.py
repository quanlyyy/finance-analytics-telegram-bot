"""Private local inference service; no paid API or user data logging."""
import base64
import httpx
from . import config

class AIUnavailable(RuntimeError):
    pass

class LocalAI:
    async def capabilities(self):
        empty = dict(voice=False, receipt=False, ai_chat=False, csv_import=True)
        if not config.AI_WORKER_URL:
            return empty
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(config.AI_WORKER_URL + '/health')
                response.raise_for_status()
                data = response.json()
                return {**empty, **{k: data.get(k) is True for k in ('voice','receipt','ai_chat')}}
        except (httpx.HTTPError, ValueError):
            return empty

    async def process(self, user, kind, **kwargs):
        if not config.AI_WORKER_URL:
            raise AIUnavailable('Локальный ИИ пока недоступен. Попробуйте позже.')
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(config.AI_WORKER_URL + '/process', json=dict(user_id=user, kind=kind, **kwargs))
                if response.status_code in (422,429,503,504):
                    detail = response.json().get('detail')
                    raise AIUnavailable(detail if isinstance(detail,str) else 'Не удалось обработать запрос.')
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError):
            raise AIUnavailable('Сервис занят или недоступен. Повторите через минуту.') from None

    async def recognize(self, user, kind, data):
        if not data or len(data) > 6_000_000:
            raise AIUnavailable('Размер файла должен быть от 1 байта до 6 МБ.')
        return (await self.process(user, kind, payload=base64.b64encode(data).decode()))['text']

provider = LocalAI()
