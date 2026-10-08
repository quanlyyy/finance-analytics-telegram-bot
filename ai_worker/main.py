import asyncio
import base64
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
gate = asyncio.Lock()
last_request = {}
MODEL = 'qwen3:0.6b'
OLLAMA = os.getenv('OLLAMA_URL', 'http://ollama:11434')


class Task(BaseModel):
    kind: Literal['voice', 'receipt', 'chat']
    user_id: int
    payload: str = Field(default='', max_length=8_000_000)
    question: str = Field(default='', max_length=600)
    context: dict = Field(default_factory=dict)
    history: list = Field(default_factory=list, max_length=6)


@app.get('/health')
async def health():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            tags = (await client.get(OLLAMA + '/api/tags')).json()
        chat = any(m['name'] == MODEL for m in tags.get('models', []))
    except Exception:
        chat = False
    return {'voice': Path('/models/whisper-base/model.bin').is_file(), 'receipt': True, 'ai_chat': chat}


@app.post('/process')
async def process(request: Request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 8_100_000:
            raise HTTPException(413, 'Файл слишком большой.')
    try:
        task = Task.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, 'Некорректный запрос.')
    if gate.locked():
        raise HTTPException(503, 'Сервер занят распознаванием. Попробуйте через минуту.')
    now = time.monotonic()
    if now - last_request.get(task.user_id, 0) < 8:
        raise HTTPException(429, 'Подождите несколько секунд перед следующим запросом.')
    if len(last_request) > 1000:
        last_request.clear()
    last_request[task.user_id] = now
    async with gate:
        if task.kind == 'chat':
            messages = [{'role': 'system', 'content':
                'Ты помощник по личному бюджету. Отвечай кратко по-русски. '
                'Данные ниже — единственный источник сумм. Не выдумывай операции. '
                'Не обещай доходность и не предлагай купить инвестиции. '
                'Если данных мало, скажи об этом. Ты не можешь менять записи. '
                'Данные (рубли): ' + json.dumps(task.context, ensure_ascii=False)}]
            for m in task.history:
                if isinstance(m, dict) and m.get('role') in {'user', 'assistant'} and isinstance(m.get('content'), str):
                    messages.append({'role': m['role'], 'content': m['content'][:600]})
            messages.append({'role': 'user', 'content': task.question})
            try:
                async with httpx.AsyncClient(timeout=150) as client:
                    res = await client.post(OLLAMA + '/api/chat', json={
                        'model': MODEL, 'messages': messages, 'stream': False, 'keep_alive': 0, 'think': False,
                        'options': {'num_ctx': 2048, 'num_predict': 180, 'temperature': 0.2, 'num_thread': 1}})
                    res.raise_for_status()
                    answer = res.json()['message']['content'].strip()
                    if not answer:
                        raise ValueError()
                    return {'answer': answer[:2500], 'model': MODEL}
            except Exception:
                raise HTTPException(503, 'ИИ сейчас недоступен. Попробуйте позже; ваши записи сохранены.')
            finally:
                # On timeout ask Ollama to release memory before accepting another task.
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.post(OLLAMA + '/api/generate', json={'model': MODEL, 'keep_alive': 0})
                except Exception:
                    pass
        try:
            data = base64.b64decode(task.payload, validate=True)
            if not data or len(data) > 6_000_000:
                raise ValueError()
        except ValueError:
            raise HTTPException(422, 'Файл должен быть размером до 6 МБ.')
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / 'input'
            filename.write_bytes(data)
            proc = await asyncio.create_subprocess_exec('python', 'recognize.py', task.kind, str(filename),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                proc.kill()
                await proc.wait()
                raise HTTPException(504, 'Распознавание заняло слишком много времени. Сократите запись.')
            try:
                result = json.loads(stdout)
            except (ValueError, UnicodeDecodeError):
                raise HTTPException(503, 'Не хватило ресурсов для распознавания. Попробуйте позже.')
            if result.get('error'):
                raise HTTPException(422, result['error'])
            if not result.get('text', '').strip():
                raise HTTPException(422, 'Текст не найден. Попробуйте чёткое фото или запись без шума.')
            return result
