import base64
from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from .auth import current_user
from .db import Session
from .finance import summary
from .integrations import provider, AIUnavailable
from .recognition import preview

router = APIRouter(prefix='/api')

def context_for(user, month):
    with Session() as session:
        data = summary(session, user, month)
    top = max(data['categories'],key=data['categories'].get) if data['categories'] else None
    return {'month': month, 'currency':'RUB', 'largest_expense_category':top, **{k:data[k]/100 for k in ('income','expense','net','budget')}, 'categories': {k:v/100 for k,v in data['categories'].items()}}

class ChatMessage(BaseModel):
    role: Literal['user','assistant']
    content: str = Field(max_length=300)

class RecognitionInput(BaseModel):
    kind: Literal['voice','receipt']
    payload: str = Field(max_length=8_000_000)

@router.post('/recognition/preview')
async def recognize(request: Request, user: int = Depends(current_user)):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>8_010_000:
            raise HTTPException(413,'Максимальный размер файла — 6 МБ.')
    try:
        body = RecognitionInput.model_validate_json(raw)
        data = base64.b64decode(body.payload, validate=True)
    except (ValueError, ValidationError):
        raise HTTPException(422,'Некорректный файл') from None
    try:
        return preview(await provider.recognize(user,body.kind,data), body.kind)
    except AIUnavailable as exc:
        raise HTTPException(503,str(exc)) from None

class ChatInput(BaseModel):
    question: str = Field(min_length=1,max_length=600)
    month: str = Field(default_factory=lambda:date.today().strftime('%Y-%m'),pattern=r'^\d{4}-\d{2}$')
    history: list[ChatMessage] = Field(default_factory=list,max_length=4)

@router.post('/ai/chat')
async def chat(body: ChatInput, user: int = Depends(current_user)):
    try:
        context = context_for(user,body.month)
    except ValueError:
        raise HTTPException(422,'Некорректный месяц') from None
    try:
        result = await provider.process(user,'chat',question=body.question,context=context,history=[m.model_dump() for m in body.history])
        return {**result,'context':context}
    except AIUnavailable as exc:
        raise HTTPException(503,str(exc)) from None
