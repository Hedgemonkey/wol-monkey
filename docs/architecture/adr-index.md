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
| ADR-13 | Worker runs as root with CAP_NET_RAW (etherwake requires geteuid==0) | Accepted |
| ADR-14 | DB port published to 127.0.0.1:5432 for host-network worker connectivity | Accepted |
| ADR-15 | Host /etc/hosts bind-mounted read-only into app container for local hostname resolution | Accepted |
| ADR-16 | StateProbe: hostname-first with ip_address fallback for DNS-unreachable hosts | Accepted |
| ADR-17 | CSS: hand-written app.css utility classes only — no Tailwind, no build step | Accepted |
| ADR-18 | Single gunicorn worker to guarantee in-process rate limiter shared state | Accepted |

Full ADR prose lives in the planning document and will be expanded per-phase.
