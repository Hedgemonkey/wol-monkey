# Architecture Decision Records

| # | Title | Status |
|---|-------|--------|
| ADR-1 | Backend framework: FastAPI | Accepted |
| ADR-2 | Database: PostgreSQL + SQLAlchemy 2.x + Alembic | Accepted |
| ADR-3 | Auth: server-side sessions + hashed API tokens | Accepted |
| ADR-4 | API/UI: single FastAPI app, server-rendered Jinja2 | Accepted |
| ADR-5 | Deployment: Docker Compose, multi-service (web/worker/db/caddy) | Accepted |
| ADR-6 | Reverse proxy: Caddy (reference) | Accepted |
| ADR-7 | State detection: pragmatic multi-signal probe (ping + TCP-SSH) | Accepted |
| ADR-8 | Settings: DB-first, env for bootstrap only | Accepted |
| ADR-9 | External port: env at the edge (Caddy), base_url in DB | Accepted |
| ADR-10 | Screenshots/docs: Playwright-generated against real app | Accepted |
| ADR-11 | Testing: pytest pyramid + Playwright e2e | Accepted |
| ADR-12 | VCS: Jujutsu colocated with git | Accepted |

Full ADR prose lives in the planning document and will be expanded per-phase.
