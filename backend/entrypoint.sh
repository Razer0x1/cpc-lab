#!/usr/bin/env sh
set -e
echo "RUN alembic upgrade head"
alembic upgrade head
exec "$@"
