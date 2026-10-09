import asyncio
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.methods import SendInvoice, SendMessage
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, Update
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import donations, config
from backend.bot import dp
from backend.db import Base, Donation, Transaction


@pytest.fixture
def sessions(monkeypatch):
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    monkeypatch.setattr(donations, 'Session', factory)
    yield factory
    engine.dispose()


def message(text=None, **fields):
    return Message.model_validate(dict(message_id=10, date=1700000000,
        chat={'id':123, 'type':'private'},
        **{'from':{'id':123, 'is_bot':False, 'first_name':'Test'}},
        text=text, **fields))


def run(awaitable):
    return asyncio.run(awaitable)


def test_support_menu_and_custom_invoice(sessions):
    menu = run(donations.donate_command(message('/donate')))
    assert menu.reply_markup.inline_keyboard[0][0].url == donations.DONATEPAY_URL
    result = run(donations.donate_command(message('/donate 150')))
    assert isinstance(result, SendInvoice)
    assert result.currency == 'XTR' and result.prices[0].amount == 150
    assert len(result.prices) == 1 and result.provider_token == ''
    with sessions() as session:
        row = session.get(Donation, result.payload[len(donations.PREFIX):])
        assert row.user_id == 123 and row.stars == 150 and row.status == 'pending'
        assert not session.scalars(select(Transaction)).all()


@pytest.mark.parametrize('text', ['/donate 0', '/donate -1', '/donate 1.5', '/donate 10001', '/donate fifty', '/donate 10 20'])
def test_invalid_amount_never_creates_invoice(sessions, text):
    assert isinstance(run(donations.donate_command(message(text))), SendMessage)
    with sessions() as session:
        assert not session.scalars(select(Donation)).all()


@pytest.mark.parametrize('user,currency,amount,payload,status,expected', [
    (123,'XTR',50,'author-support:order','pending',True),
    (456,'XTR',50,'author-support:order','pending',False),
    (123,'USD',50,'author-support:order','pending',False),
    (123,'XTR',51,'author-support:order','pending',False),
    (123,'XTR',50,'author-support:unknown','pending',False),
    (123,'XTR',50,'other:order','pending',False),
    (123,'XTR',50,'author-support:order','paid',False),
])
def test_checkout_validates_owner_amount_currency_and_state(sessions,user,currency,amount,payload,status,expected):
    with sessions() as session:
        session.add(Donation(id='order',user_id=123,stars=50,status=status))
        session.commit()
    query = PreCheckoutQuery.model_validate({'id':'checkout','from':{'id':user,'is_bot':False,'first_name':'Test'},
        'currency':currency,'total_amount':amount,'invoice_payload':payload})
    assert run(donations.pre_checkout(query)).ok is expected


def paid_message(amount=50):
    return message(successful_payment={'currency':'XTR','total_amount':amount,
        'invoice_payload':'author-support:order','telegram_payment_charge_id':'charge-123',
        'provider_payment_charge_id':''})


def test_dispatcher_records_payment_once_without_finance_entry(sessions):
    with sessions() as session:
        session.add(Donation(id='order',user_id=123,stars=50))
        session.commit()
    async def dispatch():
        async with Bot('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789') as bot:
            update = Update(update_id=1,message=paid_message())
            first = await dp.feed_update(bot, update)
            second = await dp.feed_update(bot, update)
            assert 'Спасибо' in first.text and 'уже обработан' in second.text
    run(dispatch())
    with sessions() as session:
        row = session.get(Donation,'order')
        assert row.status == 'paid' and row.charge_id == 'charge-123'
        assert len(session.scalars(select(Donation)).all()) == 1
        assert not session.scalars(select(Transaction)).all()


def test_mismatched_success_does_not_mark_paid(sessions):
    with sessions() as session:
        session.add(Donation(id='order',user_id=123,stars=50))
        session.commit()
    run(donations.successful_payment(paid_message(amount=500)))
    with sessions() as session:
        assert session.get(Donation,'order').status == 'pending'


@pytest.mark.parametrize('user',[123,456])
def test_old_refund_buttons_only_open_support(sessions,monkeypatch,user):
    monkeypatch.setattr(config, 'PAYMENT_SUPPORT_URL', 'https://t.me/example_support')
    with sessions() as session:
        session.add(Donation(id='order',user_id=123,stars=50,status='paid',charge_id='charge-123'))
        session.commit()
    callback = CallbackQuery.model_validate({'id':'cb','from':{'id':user,'is_bot':False,'first_name':'Test'},
        'chat_instance':'test','data':'refund_donation:order'})
    fake_bot = AsyncMock()
    result = run(donations.legacy_payment_support(callback.as_(fake_bot)))
    fake_bot.refund_star_payment.assert_not_called()
    assert result.chat_id == user
    assert result.reply_markup.inline_keyboard[0][0].url == 'https://t.me/example_support'
    with sessions() as session:
        assert session.get(Donation,'order').status == 'paid'


def test_payment_support_shows_only_own_receipts_and_contact(sessions,monkeypatch):
    monkeypatch.setattr(config, 'PAYMENT_SUPPORT_URL', 'https://t.me/example_support')
    with sessions() as session:
        session.add_all([Donation(id='own-order',user_id=123,stars=50,status='paid',charge_id='own-charge'),
                         Donation(id='other-order',user_id=456,stars=500,status='paid',charge_id='other-charge')])
        session.commit()
    result = run(donations.pay_support(message('/paysupport')))
    assert 'own-order' in result.text and 'other-order' not in result.text
    assert 'own-charge' not in result.text
    assert 'поможем разобраться с платежом' in result.text
    assert 'возврат' not in result.text.lower()
    assert result.reply_markup.inline_keyboard[0][0].url == 'https://t.me/example_support'
    assert all(button.callback_data is None for row in result.reply_markup.inline_keyboard for button in row)


def test_callback_invoice_is_bound_to_clicking_user(sessions):
    callback = CallbackQuery.model_validate({'id':'cb','from':{'id':123,'is_bot':False,'first_name':'Test'},
        'chat_instance':'test','data':'donate_stars:100',
        'message':{'message_id':1,'date':1700000000,'chat':{'id':123,'type':'private'},
            'from':{'id':999,'is_bot':True,'first_name':'Bot'}}})
    fake_bot = AsyncMock()
    result = run(donations.donate_stars(callback.as_(fake_bot)))
    assert isinstance(result, SendInvoice) and result.chat_id == 123
    with sessions() as session:
        assert session.scalar(select(Donation)).user_id == 123


def test_dispatcher_routes_checkout_and_support_callbacks(sessions, monkeypatch):
    async def dispatch():
        async with Bot('123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789') as bot:
            monkeypatch.setattr(bot.session, 'make_request', AsyncMock(return_value=True))
            callback = {'id':'cb','from':{'id':123,'is_bot':False,'first_name':'Test'},
                'chat_instance':'test','data':'support_author',
                'message':{'message_id':1,'date':1700000000,'chat':{'id':123,'type':'private'},
                    'from':{'id':999,'is_bot':True,'first_name':'Bot'}}}
            menu = await dp.feed_update(bot, Update.model_validate({'update_id':1,'callback_query':callback}))
            assert isinstance(menu, SendMessage) and menu.reply_markup.inline_keyboard[0][0].url == donations.DONATEPAY_URL
            callback['data'] = 'donate_stars:100'
            invoice = await dp.feed_update(bot, Update.model_validate({'update_id':2,'callback_query':callback}))
            assert isinstance(invoice, SendInvoice) and invoice.prices[0].amount == 100
            checkout = {'id':'checkout','from':callback['from'],'currency':'XTR','total_amount':100,'invoice_payload':invoice.payload}
            answer = await dp.feed_update(bot, Update.model_validate({'update_id':3,'pre_checkout_query':checkout}))
            assert answer.ok is True
    run(dispatch())
