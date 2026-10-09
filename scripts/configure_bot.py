"""Configure Telegram menu after deployment; never prints the token."""
import asyncio
from backend.telegram_client import create_bot
from backend.config import BOT_MODE
from aiogram.types import MenuButtonWebApp, WebAppInfo, BotCommand
from backend.config import BOT_TOKEN, MINI_APP_URL, WEBHOOK_SECRET, WEBHOOK_URL

async def main():
    if not MINI_APP_URL.startswith('https://'):
        raise SystemExit('HTTPS MINI_APP_URL required')
    try:
        async with create_bot() as bot:
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text='Мои финансы',web_app=WebAppInfo(url=MINI_APP_URL)))
            await bot.set_my_commands([BotCommand(command='start',description='Открыть финансового помощника'),BotCommand(command='report',description='Отчёт за месяц'),BotCommand(command='goals',description='Цели накоплений'),BotCommand(command='payments',description='Запланированные платежи'),BotCommand(command='donate',description='Сделать донат'),BotCommand(command='donations',description='История донатов'),BotCommand(command='help',description='Как пользоваться')])
            menu=await bot.get_chat_menu_button()
            print('Telegram menu configured:',menu.type)
            if WEBHOOK_SECRET and BOT_MODE == 'webhook':
                await bot.set_webhook(url=WEBHOOK_URL,secret_token=WEBHOOK_SECRET,allowed_updates=['message','callback_query','pre_checkout_query'],max_connections=1,drop_pending_updates=False)
                info=await bot.get_webhook_info()
                print('Webhook configured:',info.url,'pending:',info.pending_update_count)
    except Exception as error:
        print('Telegram configuration failed:',type(error).__name__)
        raise SystemExit(1)

if __name__=='__main__':asyncio.run(main())
