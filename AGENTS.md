# Repository Guidelines

## Project Structure & Module Organization

MediaCrawler is a Python 3.11+ crawler. `main.py` is the CLI entry point. Platform code lives in `media_platform/<platform>/`; shared abstractions are in `base/`, browser and HTTP helpers in `tools/`, caching in `cache/`, proxies in `proxy/`, database access in `database/`, and persistence adapters in `store/`. Runtime settings are under `config/`. API code and built WebUI assets are in `api/`; JavaScript helpers are in `libs/`; docs are in `docs/`. Tests are split between `tests/` and legacy `test/`; prefer `tests/` for new coverage.

## Build, Test, and Development Commands

- `uv sync` installs Python dependencies from `pyproject.toml` and `uv.lock`.
- `uv run playwright install` installs browser drivers required by crawler flows.
- `uv run main.py --help` lists crawler platforms, login types, and crawl modes.
- `uv run main.py --platform xhs --lt qrcode --type search` runs a sample Xiaohongshu search crawl.
- `uv run uvicorn api.main:app --port 8080 --reload` starts the local API/WebUI service.
- `uv run pytest tests test` runs both current and legacy test suites.
- `uv run pre-commit run --all-files` checks headers and repository hygiene.
- `npm run docs:dev` serves the VitePress docs; `npm run docs:build` builds them.

## Coding Style & Naming Conventions

Use 4-space indentation and follow the existing async-first style for network, browser, and storage paths. Keep Python modules lowercase with underscores, and keep platform-specific logic inside the matching `media_platform`, `store`, `config`, or `model` package. Add type hints to new public helpers where practical. No Black or Ruff config is present, so match nearby formatting and group imports consistently. Python files should keep the project header; use pre-commit or `tools/file_header_manager.py`.

## Testing Guidelines

Tests use `pytest` and `pytest-asyncio`. Name files `test_*.py` and functions `test_*`. Prefer deterministic unit tests for parsers, argument handling, stores, and utilities. Avoid live platform calls in normal tests; use fixtures or local sample data such as `media_platform/tieba/test_data/`. Browser or CDP tests should skip cleanly when runtime is unavailable. For targeted checks, run `uv run pytest tests/test_cdp_browser.py`.

## Commit & Pull Request Guidelines

Recent history uses concise conventional prefixes such as `fix:` and `docs:`. Keep commit subjects scoped and imperative, for example `fix: handle tieba pagination cursor`. Pull requests should describe the affected platform or subsystem, list config changes, link issues when relevant, and include screenshots for WebUI or docs changes. Always note tests run. Do not commit real cookies, tokens, browser profiles, or local data.
