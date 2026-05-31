#!/bin/bash
set -e

uv run --no-sync alembic upgrade head
exec uv run --no-sync uvicorn recipebox.main:app --host 0.0.0.0 --port 8000
