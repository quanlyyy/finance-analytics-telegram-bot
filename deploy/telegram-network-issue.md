# Telegram connectivity incident — 2026-10-08

VPS: 161.104.46.70, Ubuntu 24.04. Application: app.botsapptesses.ru.

Application is deployed remotely, Docker starts with systemd, containers have restart: unless-stopped. Local computer is not part of production serving. Mini App direct link: https://t.me/finance_analyticsmain_bot/financeapp.

The prior claim of stable Telegram delivery was premature: one webhook delivery returned 200, but subsequent deliveries again timed out.

Observed:
- Public HTTPS app and /api/health return 200.
- Unauthenticated financial API returns 401.
- Telegram getWebhookInfo reports correct IP 161.104.46.70 and Connection timed out, with pending updates.
- Both 443 and 8443 webhook delivery have timed out; one delivery on 8443 succeeded. Current registered webhook is port 8443.
- On VPS: curl -I --connect-timeout 5 --max-time 8 https://api.telegram.org timed out connecting to port 443. DNS returned 149.154.166.110.
- No public IPv6 route. No AAAA record for application.
- Local INPUT policy ACCEPT; DOCKER-USER contains no blocking rule.
- /start, /start with argument, start, старт and Старт handlers pass automated tests; replies are returned inline in webhook response.

## Текст для поддержки Selectel

На VPS 161.104.46.70 нестабильно соединение с Telegram. С сервера TCP-подключение к api.telegram.org (DNS: 149.154.166.110), порт 443, завершается тайм-аутом. В обратном направлении Telegram getWebhookInfo сообщает Connection timed out при доставке на https://app.botsapptesses.ru:8443/api/telegram/webhook; на 443 тоже были тайм-ауты. При этом сайт и /api/health доступны по HTTPS из внешней сети. Локальный firewall блокировок не показывает. Просьба проверить маршрутизацию, внешние ACL и фильтрацию между VPS и сетями Telegram. Секреты webhook и токен бота для проверки маршрута не требуются.

Do not resolve by running a bridge on the user's PC, exposing secrets, using an untrusted proxy or disabling TLS verification. After network recovery verify a fresh /start in Telegram and matching 200 webhook delivery, not merely an empty queue.
