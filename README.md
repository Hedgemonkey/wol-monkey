# WoL-Monkey 🐒

> Secure, self-hosted Wake-on-LAN control for homelab users.

[![CI](https://github.com/Hedgemonkey/wol-monkey/actions/workflows/ci.yml/badge.svg)](https://github.com/Hedgemonkey/wol-monkey/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

| Login | Dashboard | Settings |
|---|---|---|
| ![Login](docs/screenshots/02_login.png) | ![Dashboard](docs/screenshots/04_dashboard_probe.png) | ![Settings](docs/screenshots/07_settings.png) |

| Add Machine | API Docs |
|---|---|
| ![Add Machine](docs/screenshots/05_add_machine.png) | ![API Docs](docs/screenshots/08_api_docs.png) |

---

## Features

- **Web UI** — polished dashboard with live machine state (online / offline / waking)
- **Wake + Ensure-Online** — one-click wake, with optional poll-until-reachable
- **Authenticated API** — bearer token support for automation / Home Assistant
- **First-run setup wizard** — guided initial configuration with no manual config files
- **Pluggable wake strategies** — `etherwake` (raw L2) and `udp_broadcast` (no root)
- **Three deployment modes** — local-only, Tailscale/private, or public behind Caddy

---

## Quick Start

### Prerequisites

- Docker Engine ≥ 24 + Docker Compose plugin
- A machine on the **same Layer-2 network** as the targets (for `etherwake`), or any networked
  host for UDP broadcast mode.

### 1 — Clone and configure

```bash
git clone https://github.com/Hedgemonkey/wol-monkey.git
cd wol-monkey
cp .env.example .env
```

Edit `.env` and fill in at minimum:

| Variable | Description |
|---|---|
| `POSTGRES_PASSWORD` | Strong password for the database |
| `APP_SECRET` | 64-byte hex secret — `python3 -c "import secrets; print(secrets.token_hex(64))"` |

### 2 — Start the stack

```bash
# API + worker + Postgres (without Caddy TLS — suitable for LAN/Tailscale)
docker compose up -d app worker db

# With Caddy HTTPS (edit Caddyfile hostname first)
docker compose --profile caddy up -d
```

### 3 — Open the setup wizard

Navigate to `http://<host>:8000` (or your Caddy domain) and follow the five-step wizard:

1. **Welcome**
2. **Create admin account** — username + password (12+ chars)
3. **Network config** — wake interface, default strategy, poll timeout
4. **Add first machine** — or skip and add later from the dashboard
5. **Complete** 🎉

---

## API Reference

All endpoints are under `/api/`. Interactive Swagger UI is available at **`/api/docs`**.

### Authentication

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/login` | — | JSON login, returns session cookie + CSRF token |
| `POST` | `/api/auth/logout` | Session | Revoke current session |
| `GET` | `/api/auth/me` | Session **or** Bearer token | Current user info |
| `POST` | `/api/auth/tokens` | Session + CSRF | Create API token (shown once) |
| `GET` | `/api/auth/tokens` | Session | List active tokens |
| `DELETE` | `/api/auth/tokens/{token_id}` | Session + CSRF | Revoke a token |

### Machines

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/machines` | Session **or** Bearer token | List all machines |
| `POST` | `/api/machines` | Session + CSRF | Create machine |
| `GET` | `/api/machines/{id}` | Session **or** Bearer token | Get machine detail |
| `PATCH` | `/api/machines/{id}` | Session + CSRF | Update machine fields |
| `DELETE` | `/api/machines/{id}` | Session + CSRF | Delete machine |
| `GET` | `/api/machines/{id}/status` | Session **or** Bearer token | Live ping + TCP-SSH probe |

### Wake

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/machines/{id}/wake` | Session + CSRF | Queue wake job via worker |
| `POST` | `/api/machines/{id}/wake/direct` | Bearer token | Direct wake (needs `CAP_NET_RAW` for etherwake) |
| `GET` | `/api/machines/{id}/attempts/{aid}` | Session **or** Bearer token | Poll attempt status |

### Setup Wizard (pre-completion only — returns 410 afterwards)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/setup/status` | — | Current wizard state |
| `POST` | `/api/setup/admin` | — | Create admin account |
| `POST` | `/api/setup/network` | — | Save network config |
| `POST` | `/api/setup/complete` | — | Mark wizard done |

### Other

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Liveness check — `{"status":"ok","version":"0.1.0"}` |

---

## Configuration

All infrastructure configuration is via environment variables (`.env`).
User-facing settings (wake interface, strategy defaults, session lifetime) are stored in
the database and managed via the **Settings** page in the UI.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | `postgresql+asyncpg://user:pass@host/db` |
| `APP_SECRET` | — | CSRF / session signing secret (required in prod) |
| `POSTGRES_USER` | `wol` | DB username (docker-compose) |
| `POSTGRES_PASSWORD` | — | DB password (docker-compose) |
| `POSTGRES_DB` | `wolmonkey` | DB name (docker-compose) |
| `BIND_HOST` | `0.0.0.0` | Uvicorn bind address |
| `BIND_PORT` | `8000` | Uvicorn bind port |
| `TRUSTED_PROXIES` | `172.20.0.0/16` | CIDRs of trusted reverse proxies |
| `DEBUG` | `false` | Enable debug mode |
| `LOG_LEVEL` | `INFO` | Python log level |

---

## Wake Strategies

| Strategy | Value | How it works | Requirements |
|---|---|---|---|
| etherwake | `etherwake` | Layer-2 magic packet via `etherwake` binary | `CAP_NET_RAW`, same L2 segment |
| UDP broadcast | `udp_broadcast` | Magic packet over UDP to port 9 | None — works across subnets with directed broadcast |

The worker container uses `network_mode: host` and `cap_add: [NET_RAW]` for `etherwake`.
If you use `udp_broadcast` only, you can remove those from `docker-compose.yml`.

---

## Architecture

**Stack:** Python 3.12+ · FastAPI · SQLAlchemy 2.x async (asyncpg) · Alembic · PostgreSQL 16 · Jinja2 · Caddy · Docker Compose

**Layers:**
```
web/API routes  →  services  →  domain (pure Python, zero framework imports)
                       ↓
               infra / persistence  (implements domain ports)
```

**Key design decisions:**
- Domain layer has zero framework imports — trivially unit testable
- Wake jobs queued to PostgreSQL, executed by a separate worker process with `CAP_NET_RAW`
- CSRF tokens are HMAC-bound to the session's `csrf_secret` — invalidated on logout
- Passwords use Argon2id; API tokens are SHA-256 hashed at rest, shown once on creation
- UUID validation in all repository methods prevents asyncpg `DataError` on malformed IDs
- Combined `Session | Bearer` auth dependency on all read endpoints

---

## Deployment Guides

- **Local LAN** — `docker compose up -d app worker db` then open `http://<host>:8000`
- **Tailscale** — same as LAN; the Tailscale IP is accessible from all your devices
- **Public with TLS** — edit `Caddyfile` with your domain, run `docker compose --profile caddy up -d`
- **Upgrading** — `git pull && docker compose up -d --build` — migrations run automatically at startup

---

## Security

WoL-Monkey is designed secure-by-default:

- No unauthenticated access to any machine data or wake actions
- Session-based UI with CSRF double-submit on every mutating endpoint (POST/PATCH/DELETE)
- API tokens stored SHA-256 hashed; raw token shown **once** at creation
- Token auth scoped read-only; write operations always require a session + CSRF
- Privileged wake operations (`CAP_NET_RAW`) isolated in the worker container
- Caddy provides automatic TLS + `Strict-Transport-Security` + `X-Frame-Options`
- All inputs validated by Pydantic (MAC regex, IP address, enum values) before hitting the DB

---

## Developer Workflow

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Lint + type check
python -m ruff check . && python -m ruff format .
python -m mypy app worker

# Tests — unit + API (no DB required)
python -m pytest -m "not e2e and not integration"

# Integration tests (requires Postgres — uses testcontainers)
python -m pytest -m integration

# Start dev server
DATABASE_URL=postgresql+asyncpg://... APP_SECRET=... uvicorn app.main:app --reload

# Alembic migrations
alembic revision --autogenerate -m "description"
alembic upgrade head

# Live security audit (requires running server + test DB)
python tests/_security_audit.py
```

---

## SSH Auto-Wake

Connect your IDE or terminal directly to a sleeping machine — WoL-Monkey wakes
it automatically before SSH establishes the connection.

Uses SSH's `ProxyCommand` to call the API before each connection. If the
machine is already online the overhead is a single HTTP request (~5 ms). If
it's sleeping, the magic packet is sent and SSH waits until TCP/SSH responds
before proceeding.

Works with **VS Code Remote-SSH**, **Windsurf**, **Cursor**, **JetBrains
Gateway**, and plain `ssh` / `scp` / `rsync`.

```ssh-config
# ~/.ssh/config
Host my-machine
    HostName <machine-ip-or-hostname>
    User <your-username>
    ProxyCommand wol-wake <machine-uuid> %h %p
    ServerAliveInterval 30
    ServerAliveCountMax 3
```

**→ Full setup guide: [docs/guides/ssh-auto-wake.md](docs/guides/ssh-auto-wake.md)**

---

## Contributing

PRs welcome. Please follow the commit discipline (Conventional Commits, multi-line bodies for non-trivial changes).

---

## License

[MIT](LICENSE) © Hedgemonkey
