"""Validate Telegram credentials without printing credentials or sending messages."""
import asyncio
from backend.telegram_client import create_bot
from backend.config import BOT_TOKEN

async def main():
    try:
        async with create_bot() as bot:
            user = await bot.get_me()
            print(f'Bot connection OK: @{user.username}')
    except Exception as error:
        print(f'Bot connection failed: {type(error).__name__}')
        raise SystemExit(1)

if __name__ == '__main__':
    asyncio.run(main())
