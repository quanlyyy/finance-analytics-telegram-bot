"""Run in ai-worker with synthetic data only, never touches finance records."""
import base64
import io
import time
import httpx
from PIL import Image,ImageDraw,ImageFont

def main():
    client=httpx.Client(base_url='http://localhost:8080',timeout=180)
    print('capabilities',client.get('/health').json(),flush=True)
    image=Image.new('RGB',(900,650),'white')
    draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',36)
    draw.multiline_text((40,40),'ТЕСТОВЫЙ МАГАЗИН\nМОЛОКО 120.00\nХЛЕБ 50.00\nИТОГО: 170.00\nНАЛИЧНЫМИ: 200.00\nСДАЧА: 30.00',font=font,fill='black',spacing=18)
    buffer=io.BytesIO();image.save(buffer,format='PNG')
    start=time.monotonic()
    response=client.post('/process',json={'kind':'receipt','user_id':-101,'payload':base64.b64encode(buffer.getvalue()).decode()})
    print('receipt',response.status_code,response.json(),'seconds',round(time.monotonic()-start,1),flush=True)
    response.raise_for_status()
    assert '170' in response.json()['text']
    start=time.monotonic()
    response=client.post('/process',json={'kind':'chat','user_id':-102,'question':'Назови самую большую категорию расходов и дай один короткий совет.', 'context':{'currency':'RUB','income':50000,'expense':20000,'categories':{'Продукты':15000,'Кафе':5000}}})
    print('chat',response.status_code,response.json(),'seconds',round(time.monotonic()-start,1),flush=True)
    response.raise_for_status()

if __name__=='__main__':main()
