# AICTE FDR Management Portal — Complete Frontend Prototype

A frontend-only demonstration of an institution-wise Fixed Deposit Receipt (FDR) and security-deposit management portal based on **AICTE FDR Portal – Webpage Structure v2**. All data is fictional. No real AICTE or bank service is connected.

## Run locally

Requirements: Node.js 18+ and npm.

```bash
npm install
npm run dev
```

Open the local URL printed by Vite. Validate the project with:

```bash
npm run build
npm run lint
npm test
```

## Demo accounts

Password for all demo accounts: `demo123`

- `admin@demo.test` — Administrator
- `institution@demo.test` — Institution User
- `officer@demo.test` — Scrutiny Officer
- `auditor@demo.test` — Auditor

Use the clearly labelled **DEMO: switch role** control to exercise different role views. Role switching is a development convenience, not authentication.

## Included

- React 18, TypeScript, Vite, React Router, TanStack Query, Zod, Tailwind CSS, date-fns, and i18n scaffolding.
- Demo login and role-aware navigation, including institution-scoped FDR visibility.
- Institution management with search, editing, add/deactivate flows and audit entries.
- All FDR register view with search, status filtering, derived days-to-maturity, details dialog, CSV export and role scoping.
- FDR registration form with date/amount checks, configurable bank/category lists, and a file picker (the file is validated and stored by the backend once the upload is wired into the form).
- CSV template download and basic row-by-row import validation (valid rows imported; invalid/duplicate rows skipped).
- Verification workspace with bank confirmation fields and disabled Verified action until confirmation and reason are present.
- Query-raise action, status transitions, maturity views, renewal/release request creation, request listing, reports and CSV export, notification inbox, audit log view/export, and administrator settings.
- Domain logic and unit tests for FDR status transitions, verification rules, maturity, permissions, currency formatting, and import validation.

## Folder map

- `src/api/` — typed service modules that call the Django REST API (`http.ts` is the fetch wrapper; the Vite dev server proxies `/api` to the backend).
- `src/domain/` — status machine, verification rules, maturity and permissions.
- `src/features/` — page components and institution management.
- `src/components/` — application layout and navigation.
- `src/routes/` — route guards.
- `src/types/` — shared data models.
- `src/utils/` — formatting helpers.
- `src/i18n/` — English i18n scaffolding.

## Persistence and API replacement

All data now comes from the Django backend and PostgreSQL (see `../backend/README.md`). The former browser-only mock store has been removed; `src/test/seedFixture.ts` is kept only as a unit-test fixture.

## Important prototype limitations

- **Cosmetic/frontend-only security:** demo login, role switching, route restrictions, permissions, and separation-of-duties checks are not secure authorization. Real enforcement must be server-side.
- File selection is simulated; file bytes are not uploaded, stored, previewed or virus-scanned. A filename alone is not proof of a document.
- Bank confirmation is recorded by an officer; there is no bank integration.
- Email/OTP/password change are not connected. Notification and reminder generation is only represented by demo records, not a real scheduler or delivery service.
- CSV import supports a simple CSV format; quoted commas/embedded newlines and full spreadsheet formats are not fully parsed. Invalid rows are skipped; a detailed downloadable error report is not yet complete.
- Report CSV exports are functional, but PDF export is not implemented.
- Request tracking is a prototype. Full authorized officer recommendation/final-approval workflow and comprehensive separation-of-duties enforcement are not complete.
- Renewal-chain creation, document versioning/re-upload storage, escalation contacts/history, every listed filter/sort/pagination control, and full end-to-end workflows need further completion before production or formal acceptance.
- The seven automated checks are pure domain rules, but they are not all surfaced as a full verification-results panel in the UI.
- Audit log entries are append-only through the UI/service paths in this demo, but browser storage can be altered by a user and is not tamper-resistant.
- Build, lint and tests must be run locally after dependency installation; do not treat a successful ZIP creation as evidence that these commands passed.

## Source-document notes

The source document's permission matrix reserves institution/user management for administrators, so this prototype restricts Institution Management to the Administrator role. The source document lists bank verification as mandatory before an FDR can become Verified; the UI blocks that action until a confirmation record and reason are present.
