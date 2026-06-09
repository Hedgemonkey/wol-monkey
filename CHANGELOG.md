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
- Setup wizard API: `GET /setup/status`, `POST /setup/admin`, `POST /setup/network`,
  `POST /setup/complete` — all return 410 after wizard completes
- 23 new tests; 118 total

**Phase 5 — Machines CRUD + wake API**
- `GET/POST /machines`, `GET/PATCH/DELETE /machines/{id}` — full CRUD with session auth + CSRF
- `POST /machines/{id}/wake` — queues job via worker (session + CSRF)
- `POST /machines/{id}/wake/direct` — direct wake with API token (for automation)
- `GET /machines/{id}/attempts/{aid}` — attempt status polling
- `GET /machines/{id}/status` — live ping + TCP probe result
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

**Phase 7 — Deployment**
- `Dockerfile`: single image for API + worker; includes `etherwake` + `iputils-ping`
- `docker-compose.yml`: `db`, `migrate` (one-shot), `app`, `worker`, `caddy` (optional profile)
  - Worker uses `network_mode: host` + `cap_add: NET_RAW` for L2 wake
  - `depends_on` with health-checks ensures migration runs before app/worker start
- `Caddyfile`: HTTPS reverse-proxy with security headers
- `.env.example`: updated with `POSTGRES_*` vars for docker-compose
- `README.md`: full Quick Start, API reference, configuration table, wake strategy guide,
  deployment options, and developer workflow

---

## [0.1.0] — TBD

_First public release. See [Unreleased] for current work._

<!-- Links -->
[Unreleased]: https://github.com/Hedgemonkey/wol-monkey/compare/HEAD...HEAD
