"""Synthetic Russian fixture. piper-tts is needed only in the test container."""
import base64
import tempfile
import subprocess
import time
import sys
from pathlib import Path
import httpx

with tempfile.TemporaryDirectory() as directory:
    audio=Path(directory)/'sample.wav'
    model=Path(directory)/'ru_RU-irina-medium.onnx'
    for suffix in ('','.json'):
        url='https://huggingface.co/rhasspy/piper-voices/resolve/main/ru/ru_RU/irina/medium/'+model.name+suffix
        r=httpx.get(url,follow_redirects=True,timeout=120);r.raise_for_status()
        Path(str(model)+suffix).write_bytes(r.content)
    subprocess.run([sys.executable,'-m','piper','-m',str(model),'-f',str(audio)],input='Я потратил двести рублей на кофе.',text=True,check=True)
    started=time.monotonic()
    response=httpx.post('http://localhost:8080/process',json={'user_id':-103,'kind':'voice','payload':base64.b64encode(audio.read_bytes()).decode()},timeout=180)
    print('voice',response.status_code,response.json(),'seconds',round(time.monotonic()-started,1),flush=True)
    response.raise_for_status()
    text=response.json()['text'].lower()
    assert 'кофе' in text and ('двести' in text or '200' in text), text
