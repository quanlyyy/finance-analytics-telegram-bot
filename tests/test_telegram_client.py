import pytest
from backend import config
from backend.telegram_client import create_bot

def test_proxy_validation_hides_credentials(monkeypatch):
    monkeypatch.setattr(config,'BOT_PROXY_URL','https://user:private-password@example.test:3128')
    with pytest.raises(ValueError) as error:create_bot()
    assert 'private-password' not in str(error.value)

def test_valid_proxy_and_direct_session(monkeypatch):
    monkeypatch.setattr(config,'BOT_TOKEN','123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789')
    for proxy in ['', 'http://127.0.0.1:3128','socks5://user:password@127.0.0.1:1080']:
        monkeypatch.setattr(config,'BOT_PROXY_URL',proxy)
        bot=create_bot()
        assert bot.session.proxy==(proxy or None)
