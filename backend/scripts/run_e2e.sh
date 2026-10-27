#!/bin/bash
# Fresh database every run: the scenario writes data, so each run must start clean.
set -e
cd /home/claude/w/proj/backend
export PYTHONPATH=/home/claude/up/aicte-fdr-management-portal-complete-with-database/aicte-fdr-management-portal-complete/.venv/Lib/site-packages DB_ENGINE=sqlite DJANGO_DEBUG=1 FDR_DEMO_MODE=1 DJANGO_SECRET_KEY=test-key
rm -f db.sqlite3; rm -rf private_media
python3 manage.py migrate -v0
python3 manage.py seed_demo > /dev/null
python3 manage.py shell < scripts/e2e.py 2>/tmp/e2e.err
