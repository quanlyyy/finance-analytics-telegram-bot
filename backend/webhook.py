"""Telegram webhook with authenticated ingress and inline Bot API responses."""
import asyncio
import hmac
from fastapi import APIRouter, Request, HTTPException
from aiogram import Bot
from aiogram.methods import TelegramMethod
from aiogram.types import Update
from pydantic import ValidationError
from . import config
from .bot import dp

router=APIRouter()
lock=asyncio.Lock()

@router.post('/api/telegram/webhook')
async def receive(request:Request):
    supplied=request.headers.get('X-Telegram-Bot-Api-Secret-Token','')
    if not config.WEBHOOK_SECRET or not hmac.compare_digest(supplied,config.WEBHOOK_SECRET):
        raise HTTPException(403,'Forbidden')
    if config.BOT_MODE != 'webhook':
        raise HTTPException(409,'Webhook is disabled')
    if not config.BOT_TOKEN:raise HTTPException(503,'Bot is not configured')
    try:
        update=Update.model_validate(await request.json())
    except (ValueError,ValidationError):raise HTTPException(422,'Invalid update')
    async with lock:
        async with Bot(config.BOT_TOKEN) as bot:
            result=await dp.feed_update(bot,update)
            if not isinstance(result,TelegramMethod):return {}
            payload={'method':result.__api_method__}
            for key,value in result.model_dump(warnings=False).items():
                prepared=bot.session.prepare_value(value,bot=bot,files={},_dumps_json=False)
                if prepared is not None:payload[key]=prepared
            return payload
