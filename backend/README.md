# AICTE FDR Portal — Backend and Database

Django + Django REST Framework API with a PostgreSQL database, built from the spec's Section 9. The React frontend (`aicte-fdr-phase1/`) calls this API.

## What is in place

- **Database schema** (`fdr/models.py`): institutions, users, FDRs, documents (versioned, checksummed), verifications, queries, release/renewal requests, notifications, settings and the audit log.
- **Database rules** (spec 9.4): money stored as integer paise; unique FDR number per bank (case-insensitive); unique institution code; maturity must follow issue; amount must be positive; indexes for dashboards; no hard deletes; append-only audit table with a PostgreSQL trigger (`apply_db_guards`).
- **Business rules** (`fdr/domain.py`): a pure Python module with no Django import. It holds the status machine, role matrix, separation of duties, money and date handling, the seven automated checks, file-type detection by signature, and CSV parsing. It is unit-tested without a database.
- **Workflows** (`fdr/services.py`): every status change, bank confirmation, request and import runs in one transaction, with the row locked and the audit entry written in the same transaction.
- **API** (`fdr/views.py`, `fdr/urls.py`): the endpoints the frontend uses, plus the spec's main endpoints (see below).
- **Demo data** (`seed_demo`) and a **daily job** (`run_jobs`: maturity check and reminders, safe to re-run).

## Not yet built

- Malware scanning: uploads are stored with `scan_status = pending`. Connect a scanner before real use.
- Account lockout after failed logins, OTP and password reset.
- Overdue escalation and query follow-up reminders (the maturity check and reminders are built).
- Reply-to-query UI and renewal chain creation in the frontend.
- PDF export (CSV only).
- Sessions with an inactivity timeout (tokens do not expire yet).

## Requirements

- Python 3.11 or newer
- PostgreSQL 14 or newer, **or** Docker Desktop (the compose file starts PostgreSQL for you)

## Option A — Docker (simplest)

From the project root (the folder that contains `docker-compose.yml`):

```
copy backend\.env.example backend\.env
docker compose up --build
```

The API starts on `http://localhost:8000`. The first start creates the tables, applies the audit guard and loads the demo data.

## Option B — Local Python and PostgreSQL (Windows)

1. Install PostgreSQL and create a database named `aicte_fdr` with a user `aicte`. Note the password.
2. Activate the virtual environment that is already in the project root:
   ```
   cd "aicte-fdr-management-portal-complete"
   ..\.venv\Scripts\activate
   cd backend
   pip install -r requirements.txt
   ```
3. Create `backend\.env` from the example and set `POSTGRES_PASSWORD`:
   ```
   copy .env.example .env
   ```
4. Create the schema and load the demo data. Run these once:
   ```
   python manage.py makemigrations fdr
   python manage.py migrate
   python manage.py apply_db_guards
   python manage.py seed_demo
   ```
5. Start the API:
   ```
   python manage.py runserver
   ```
6. In a second terminal, start the frontend from `aicte-fdr-phase1`: `npm run dev`. Open the URL Vite prints. Requests to `/api` are forwarded to port 8000.

Demo accounts (password `demo123`): `admin@demo.test`, `officer@demo.test`, `institution@demo.test`, `auditor@demo.test`.

### Quick demo without PostgreSQL

Set `DB_ENGINE=sqlite` in `.env`, then run steps 4–6. The database guard is skipped on SQLite; the application still refuses audit changes.

## Migrations

`makemigrations` generates the first migration from `fdr/models.py`. After it runs, **commit the generated `fdr/migrations/0001_initial.py`** and stop running `makemigrations` in production. The Docker command runs it on each start only so the demo works from a clean clone; that is not suitable for a real deployment.

## Scheduled job

Configure SMTP in `backend\.env` (`EMAIL_HOST`, `EMAIL_PORT`, credentials, TLS/SSL, and
`DEFAULT_FROM_EMAIL`) and provide an email on each institution's contact record. The daily
job sends one email at each configured maturity threshold (90, 60, and 30 days by default);
it also creates the existing in-portal notification. A unique record prevents repeat emails
if the job is run again for the same FDR and threshold. SMTP failures are reported by the job
so they can be corrected and retried.

Run once a day (Windows Task Scheduler or cron):

```
python manage.py run_jobs
```

It moves FDRs to Nearing Maturity and Matured as their dates arrive, creates in-portal reminders,
and sends maturity emails. Running it twice creates no duplicate reminders or emails.

## Testing

Four layers, all of which passed on the final build (Python 3.12 with the Django 5.1.4 and DRF 3.15.2 pinned in `requirements.txt`, SQLite):

- 24 pure rule tests (no database): `python -m unittest fdr.tests.test_domain`
- 41 Django tests (API, workflow, database rules): `python manage.py test fdr`
- 49 end-to-end checks through the API: `python manage.py shell < scripts/e2e.py` on a freshly seeded database (`scripts/run_e2e.sh` on Linux/macOS does the reset for you)
- 18 further endpoint checks: `python manage.py shell < scripts/e2e2.py`, run after `e2e.py`

The end-to-end scripts write data, so reset the database before each run.

```
python -m unittest fdr.tests.test_domain          # rule tests; no database needed
python manage.py test fdr                          # API and database tests; needs the database
```

For the database tests on SQLite, set `DB_ENGINE=sqlite` first.

## API summary

All routes are under `/api/` and need a token (`Authorization: Token <key>`) except login and the demo routes.

| Method | Route | Purpose |
|---|---|---|
| POST | `auth/login/` | Sign in; returns a token |
| POST | `auth/logout/` | Sign out |
| GET | `auth/me/` | Current user |
| GET | `workspace/` | Everything the workspace needs, filtered by role |
| GET, POST | `institutions/` | List (scoped) / create (administrator) |
| PATCH | `institutions/{id}/` | Edit or deactivate (administrator) |
| GET, POST | `fdrs/` | Search (scoped) / register |
| POST | `fdrs/import/` | Bulk import (CSV file or rows); bad rows are reported |
| GET | `fdrs/{id}/` | Detail with documents, verifications, queries, requests |
| POST | `fdrs/{id}/documents/` | Upload a new document version |
| POST | `fdrs/{id}/verify/` | Re-run the automated checks |
| POST | `fdrs/{id}/transition/` | Change status (rules and roles enforced) |
| POST | `fdrs/{id}/bank-confirmation/` | Record bank confirmation |
| POST | `fdrs/{id}/requests/` | Submit a release or renewal request |
| POST | `queries/{id}/reply/` | Institution answers a query |
| POST | `requests/{id}/recommend/` | Officer recommendation |
| POST | `requests/{id}/decision/` | Administrator approves or rejects a recommended release |
| GET | `documents/{id}/download/` | Download, checked against role and institution |
| GET | `reports/{name}/` | CSV export of visible records |
| GET | `notifications/`, POST `notifications/{id}/read/` | Inbox |
| GET | `audit-logs/` | Audit history (administrator, auditor; officers see FDR entries) |
| GET, PUT | `settings/` | Thresholds and configuration (administrator) |

## Security notes

- Passwords are hashed with Argon2 (Django falls back to PBKDF2 only if `argon2-cffi` is missing).
- The server decides every permission. The frontend only hides buttons.
- Institution users get `404` for another institution's records, so the existence of those records is not revealed.
- Uploaded files are stored outside the web folder under random names. The file type is read from its first bytes, not from the name or the browser.
- Set `FDR_DEMO_MODE=0` before any real use. That turns off the demo accounts and the role switcher.
- Use HTTPS in production (`DJANGO_SECURE_SSL_REDIRECT=1`, the default when `DJANGO_DEBUG=0`).
- Never commit `backend/.env`.
- The server refuses to start with `DJANGO_DEBUG=0` while `DJANGO_SECRET_KEY` is still a placeholder.
- If Argon2 cannot load on a machine, the server falls back to PBKDF2 automatically.
- `docker-compose.yml` forces `DB_ENGINE=postgres` for the API container, so a local `.env` set to SQLite does not affect it.
