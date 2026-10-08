import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./data/finance.db')
MINI_APP_URL = os.getenv('MINI_APP_URL', '')
DEV_AUTH = os.getenv('DEV_AUTH', 'false').lower() == 'true'
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', '')
WEBHOOK_URL = os.getenv('WEBHOOK_URL', MINI_APP_URL.rstrip('/')+'/api/telegram/webhook')
BOT_PROXY_URL = os.getenv('BOT_PROXY_URL', '').strip()
BOT_MODE = os.getenv('BOT_MODE', 'webhook')
