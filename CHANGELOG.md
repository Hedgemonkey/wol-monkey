# Changelog

All notable changes to WoL-Monkey will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Project scaffolding: FastAPI app factory, `GET /api/health` endpoint
- Layered directory structure (domain/services/infra/persistence/api/web/security)
- `pyproject.toml` with ruff, mypy, pytest configuration
- `Makefile` with fmt/lint/type/test/migrate/dev/up/down/backup/restore targets
- GitHub Actions CI workflow (quality + unit/api/security + integration with Postgres)
- `.pre-commit-config.yaml` (ruff format + lint, trailing whitespace, YAML/TOML checks)
- `.env.example` with all supported environment variables documented
- README skeleton with features, quick start, architecture overview, deployment guides
- CHANGELOG (this file)

---

## [0.1.0] — TBD

_First public release. See [Unreleased] for current work._

<!-- Links -->
[Unreleased]: https://github.com/Hedgemonkey/wol-monkey/compare/HEAD...HEAD
