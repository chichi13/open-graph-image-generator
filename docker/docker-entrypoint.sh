#!/bin/sh
set -e

# Default command is 'api' if nothing is passed
COMMAND=${1:-api}


if [ "$COMMAND" = "api" ]; then
  # Apply database migrations before starting services
  echo "Running database migrations..."
  # Use the activated venv path directly
  /app/.venv/bin/alembic upgrade head
  echo "Migrations complete."
  echo "Starting FastAPI server..."
  # Use the activated venv path directly
  exec /app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

elif [ "$COMMAND" = "worker" ]; then
  echo "Starting Celery worker..."
  # Use the activated venv path directly
  exec /app/.venv/bin/celery -A app.celery_app worker --loglevel=info

else
  # Allow running other commands passed to the container
  echo "Running command: $@"
  exec "$@"
fi 