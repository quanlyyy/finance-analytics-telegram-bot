# Optional outbound Telegram proxy

## Deployment status — 2026-10-08

The user-supplied HTTP CONNECT proxy passed Telegram getMe from the VPS. Production now uses BOT_MODE=polling. Telegram reports no webhook, no pending updates, and no webhook error. Bot and API containers are running; API health and signed Mini App authentication checks passed. Docker is enabled at boot and the bot uses restart: unless-stopped. Proxy credentials are stored only in ignored environment files, not this document. A fresh /start from the user's Telegram account still needs confirmation. Keep the proxy subscription active for outbound Telegram connectivity.

`aiohttp-socks` and `AiohttpSession` are supported through `BOT_PROXY_URL` in `.env`. No proxy is configured by default. `proxy.server:3128` from the pasted PythonAnywhere example is not a proxy provisioned for this VPS.

Use a user-controlled or explicitly trusted HTTP CONNECT, SOCKS4 or SOCKS5 endpoint. Store credentials only in `.env`, not the repository. TLS certificate verification stays enabled. Changing the proxy does not fix inbound webhook connectivity.

Switch procedure after a real endpoint is supplied:

1. Set BOT_PROXY_URL in the local and server `.env` without printing it.
2. Build the updated server image; use `docker compose run --rm --no-deps bot python -m scripts.check_bot` to verify getMe through the proxy.
3. Only after the check succeeds, set BOT_MODE=polling and run `docker compose --profile polling up -d --build api bot`.
4. The polling runner verifies getMe, then removes the webhook without dropping pending updates, then starts long polling. The webhook API rejects further updates while in polling mode.
5. Verify fresh /start, finance entry and response from an actual Telegram user. Docker restart policy keeps the remote service running; no local PC bridge is used.

Do not activate polling or claim the network fault resolved until a real proxy passes the connection test. For rollback, set BOT_MODE=webhook, stop the polling service and re-register the webhook with scripts.configure_bot from a network that reaches Telegram.
