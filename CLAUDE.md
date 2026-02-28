# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`govec` is a Python library managed with `uv`. Python 3.13 is required (pinned in `.python-version`).

## Commands

```bash
# Install dependencies and set up environment
uv sync

# Format code
task fmt

# Check formatting and types (ruff + pyright)
task fmt-check

# Add a dependency
uv add <package>

# Build the package
uv build
```

## Structure

- `src/govec/` — library source, using `src` layout
- `scripts/` — dev scripts invoked via `Taskfile.yaml` (`fmt`, `fmt-check`)
- `pyproject.toml` — project metadata and build config (build backend: `uv_build`)
- `uv.lock` — lockfile, always commit this
- `py.typed` marker is present, so the package ships type hints

## Notes

- Build backend is `uv_build`, which only discovers packages under `src/`. Keep library code under `src/govec/`.
- No test framework is set up yet; add one via `uv add --group test pytest` when needed