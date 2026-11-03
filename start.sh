#!/bin/sh
set -eu
python -m flask --app app init-db
python -m flask --app app create-admin
exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 2 --threads 2 --timeout 120 app:app
