# Changelog

All notable changes to WoL-Monkey will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

**Phase 0 — Scaffolding + CI**
- Project scaffolding: FastAPI app factory, `GET /api/health` endpoint
- Layered directory structure: `domain / services / infra / persistence / api / web / security / worker`
- `pyproject.toml` with hatchling build, ruff, mypy (strict), pytest configuration
- `Makefile` with fmt/lint/type/test/migrate/dev/up/down/backup/restore targets
- GitHub Actions CI workflow (quality → unit/api/security → integration with Postgres)
- `.pre-commit-config.yaml` (ruff format + lint, trailing whitespace, YAML/TOML checks)
- `.env.example` with all supported environment variables documented

**Phase 1 — Persistence layer**
- SQLAlchemy 2.x async models: `User`, `Session`, `ApiToken`, `Machine`,
  `WakeAttempt`, `WakeJob`, `ProbeResult`, `SetupState`, `Setting`
- Repository ABC ports in `app/domain/ports.py`
- `Sql*Repository` implementations for all models
- Alembic migrations with timezone-aware timestamps throughout
- Testcontainers integration tests for all repositories

**Phase 2 — Auth, sessions, tokens, CSRF**
- Argon2id password hashing (`argon2-cffi`); automatic rehash on login
- API token generation: `wm_<prefix>_<secret>` format, SHA-256 hashed at rest
- CSRF tokens scoped to session `csrf_secret` via `itsdangerous`
- `AuthService`: login/logout, session validation, admin bootstrap, API token CRUD
- FastAPI security dependencies: `CurrentUser`, `CsrfProtected`, `ApiToken`
- Auth API endpoints: `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`,
  `POST/GET/DELETE /auth/tokens`
- 22 auth unit tests + 7 API endpoint tests

**Phase 3 — Domain, strategies, probe, services, worker**
- Framework-free domain entities: `Machine`, `WakeAttempt` (state machine with
  `can_transition_to()` / `is_terminal`), `ProbeResult`
- `StrEnum` status types: `AttemptStatus`, `MachineState`, `ProbeState`, `WakeStrategy`
- `WakeStrategyPort` ABC with `EtherwakeStrategy` (subprocess) and `UdpBroadcastStrategy`
  (raw socket broadcast) implementations; `get_strategy()` factory
- `StateProbe`: concurrent `ping` + TCP-SSH online detection
- `WakeService`: machine lookup → attempt creation → strategy dispatch → error recording
- `EnsureOnlineService`: configurable poll loop with WAKING→ONLINE/TIMEOUT/FAILED transitions
- `worker/main.py`: async job loop with `SIGTERM`/`SIGINT` shutdown, signal handling
- `worker/job_queue.py`: DB-backed queue using `SELECT FOR UPDATE SKIP LOCKED`
- 42 new unit tests; 95 total

**Phase 4 — Settings and setup wizard**
- `SettingsService`: typed `get_str/get_int/get_bool/set/get_all` delegating to `SettingsRepository`
- `SetupStateService`: five-step wizard state machine with `advance()`, `reset()`, `is_complete()`
- Setup wizard API: `GET /api/setup/status`, `POST /api/setup/admin`, `POST /api/setup/network`,
  `POST /api/setup/complete` — all return 410 after wizard completes
- 23 new tests; 118 total

**Phase 5 — Machines CRUD + wake API**
- `GET/POST /api/machines`, `GET/PATCH/DELETE /api/machines/{id}` — full CRUD with session auth + CSRF
- `POST /api/machines/{id}/wake` — queues job via worker (session + CSRF)
- `POST /api/machines/{id}/wake/direct` — direct wake with API token (for automation)
- `GET /api/machines/{id}/attempts/{aid}` — attempt status polling
- `GET /api/machines/{id}/status` — live ping + TCP-SSH probe result
- FastAPI `dependency_overrides` pattern established in tests for isolation
- 11 new API tests; 129 total

**Phase 6 — Web UI**
- Jinja2 templates: `base.html`, `login.html`, `machines.html`, `machine_form.html`,
  `setup_wizard.html`, `settings.html`
- Machines dashboard: live status badge, one-click Wake + Probe buttons, attempt polling loop
- Hand-written utility CSS (`app/static/css/app.css`) — no build step required
- Shared JS helpers (`app/static/js/app.js`): `getCsrf()`, `apiFetch()`
- `web_router` serving all server-rendered pages; `StaticFiles` mount at `/static`
- Web session guard (`_require_web_auth`) on all machine/settings pages
- Web form login at `POST /auth/login` (separate from JSON API at `POST /api/auth/login`)

**Phase 7 — Deployment**
- `Dockerfile`: single image for API + worker; includes `etherwake` + `iputils-ping`
- `docker-compose.yml`: `db`, `migrate` (one-shot), `app`, `worker`, `caddy` (optional profile)
  - Worker uses `network_mode: host` + `cap_add: NET_RAW` for L2 wake
  - `depends_on` with health-checks ensures migration runs before app/worker start
- `Caddyfile`: HTTPS reverse-proxy with security headers
- `.env.example`: all supported vars documented with descriptions
- `README.md`: full Quick Start, API reference, configuration table, wake strategy guide,
  deployment options, developer workflow, and Playwright-generated screenshots

**Phase 8 — Live testing + security hardening**
- Fixed `WakeStrategy` enum: renamed `UDP = "udp"` → `UDP_BROADCAST = "udp_broadcast"`
  throughout domain, infra, templates, tests; Alembic migration `7da1313001d6` to backfill data
- Fixed `WakeRequest` schema: `strategy_override: str | None` replaced with
  `strategy: WakeStrategy | None` — invalid values now return 422 instead of passing through
- Fixed wake endpoint FK violation: `await db.commit()` before `queue.enqueue()` so the
  `wake_attempt` row is visible to the worker's separate session
- Fixed MAC address validation: added `_MAC_RE` regex validator to `MachineCreate` and
  `MachineUpdate` — rejects 5-group MACs (`00:00:00:00:00`), invalid hex, wrong separators
- Fixed IP address validation: `ipaddress.ip_address()` check on `ip_address` and
  `broadcast_address` fields in `MachineCreate` — prevents asyncpg MACADDR/INET crash
- Added `_is_valid_uuid` guard in all repository `get_by_id`, `update`, `delete` methods —
  malformed IDs return `None` / no-op instead of propagating `asyncpg.DataError`
- Added `user_id` to `ApiTokenRecord` and `SqlApiTokenRepository.create` —
  Alembic migration `09d75b0dfde5` adds column with backfill
- Added `get_user_from_session_or_token` combined dependency — all read endpoints now accept
  either a session cookie or a `Authorization: Bearer wm_<prefix>_<secret>` token
- Added `tests/_security_audit.py`: 74-check live security and functional audit covering
  unauthenticated access, CSRF bypass, MAC/IP/strategy input fuzzing, session revocation,
  UUID injection, content-type confusion, API token isolation, CSRF reuse, live TCP-SSH probe,
  and wake packet dispatch monitoring against real hardware (Fedora PC at 172.24.0.2)

---

## [0.1.0] — TBD

_First public release. See [Unreleased] for current work._

<!-- Links -->
[Unreleased]: https://github.com/Hedgemonkey/wol-monkey/compare/HEAD...HEAD
