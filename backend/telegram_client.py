from urllib.parse import urlsplit
from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from . import config

def create_bot(*, use_proxy=True):
    proxy=config.BOT_PROXY_URL if use_proxy else ''
    if proxy:
        try:
            parsed=urlsplit(proxy)
            if parsed.scheme not in {'http','socks4','socks5'} or not parsed.hostname or not parsed.port:
                raise ValueError()
        except ValueError:
            raise ValueError('BOT_PROXY_URL requires http/socks4/socks5://host:port; value hidden') from None
    return Bot(config.BOT_TOKEN,session=AiohttpSession(proxy=proxy or None,timeout=60))
