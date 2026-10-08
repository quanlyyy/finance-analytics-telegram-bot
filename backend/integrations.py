"""Provider boundary. Paid AI calls are disabled until explicitly configured."""
from typing import Protocol

class AIUnavailable(RuntimeError):
    pass

class FinanceAI(Protocol):
    async def transcribe(self, audio:bytes, mime_type:str)->str: ...
    async def receipt(self, image:bytes, mime_type:str)->dict: ...
    async def advise(self, question:str, summary:dict)->str: ...

class DisabledAI:
    async def transcribe(self, audio:bytes, mime_type:str)->str:
        raise AIUnavailable('Распознавание голоса пока не подключено. Отправьте расход текстом: кофе 250.')
    async def receipt(self, image:bytes, mime_type:str)->dict:
        raise AIUnavailable('Распознавание чеков пока не подключено. Добавьте сумму вручную.')
    async def advise(self, question:str, summary:dict)->str:
        raise AIUnavailable('ИИ-провайдер пока не настроен. Доступны расчёты и советы по вашим операциям.')

provider:FinanceAI=DisabledAI()
