# Deployment handoff

Target host: 161.104.46.70. Domain: app.botsapptesses.ru.

DNS A was verified on 2026-10-08. Do not assume the application is deployed until HTTPS and the API health endpoint are verified.

The public SSH key authorizes this workstation only; the private key is in `.deploy/`, excluded from Git and Docker. Never upload `.deploy/` to the server or publish `.env`.

Before deployment, inspect OS, available memory/disk, existing services, open ports and `/opt/expense-analytics` to avoid replacing unrelated apps. Preserve any existing installation and database. Deploy app code with `.env` separately, mode 600, and DEV_AUTH=false. Domain TLS is configured by Caddy. Never expose port 8000 or a database publicly.

The first deployment needs Docker Engine and the Compose plugin from the official distribution repository. Build resources need to be checked on the VPS. Services use a persistent named database volume. Daily consistent SQLite backups should use Python sqlite3.Connection.backup, not a live filesystem copy.

Do not run a second Telegram polling instance while the deployed bot is active. Configure Telegram menu URL only after the HTTPS endpoint is reachable. No paid AI provider has been authorized or configured.
