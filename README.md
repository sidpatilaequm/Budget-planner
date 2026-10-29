# Budget planner

A school budget planner with these parts:

- **React** frontend, built with Vite.
- **Python** middleware: a FastAPI REST API.
- **MySQL 8** database.

It plans income and expenses month by month (April to March) under heads, with installment subtotals. Other features:

- Next-year planning by %, with fixed heads and a fixed total.
- Budget limits.
- Users, roles and head-level access.
- An activity log.
- Excel import and export in the `Budget_26-27.xlsx` layout.

Version 2 adds:
- **Actuals:** from Tally through a small bridge or a direct connection, or entered and imported here.
- **Budget vs actual.**
- **Planning from actuals or a forecast.**
- **TDS:** a report and alerts under the Income-tax Act, 2025 (section 393).
- **Budget simulations.**

See **[docs/VERSION-2.md](docs/VERSION-2.md)** for the update steps and how each part works.

```
budget-planner/
├── backend/            FastAPI app (Python 3.11+)
│   ├── app/
│   │   ├── main.py         app setup, CORS, table creation
│   │   ├── db.py           settings and database session
│   │   ├── models.py       tables
│   │   ├── catalog.py      permissions, default roles, standard heads
│   │   ├── security.py     bcrypt passwords, JWT, permission checks
│   │   ├── routers/        auth, admin (users/roles/activity), budget, plan_files
│   │   └── services/       budget maths and limits, planning engine, Excel
│   └── tests/test_api.py
├── frontend/           React app
│   └── src/  App.jsx, lib.js (helpers + API client), ui.jsx, components/
├── database/schema.sql MySQL schema (optional; the API creates missing tables)
├── docker-compose.yml
└── .env.example
```

## Quick start with Docker

```bash
cp .env.example .env        # then edit the passwords and JWT_SECRET
docker compose up -d --build
```

Open http://localhost:8080. The first visit asks you to create the administrator account. That step also creates the four standard roles and FY 2026–27 with all heads and lines from your workbook.

## Running without Docker

**1. MySQL**

```sql
CREATE DATABASE budget_planner CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'budget'@'%' IDENTIFIED BY 'a-strong-password';
GRANT ALL ON budget_planner.* TO 'budget'@'%';
```

You can also run `database/schema.sql` yourself. If you don't, the API creates any missing tables when it starts.

**2. Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL="mysql+pymysql://budget:a-strong-password@localhost:3306/budget_planner?charset=utf8mb4"
export JWT_SECRET="a-long-random-string"
uvicorn app.main:app --reload --port 8000
```

Interactive API docs are at http://localhost:8000/docs.

**3. Frontend**

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, forwards /api to port 8000
npm run build        # production files in dist/
```

In production, serve `dist/` from any web server and forward `/api/` to the backend. `frontend/nginx.conf` shows how.

### Settings (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `mysql+pymysql://budget:budget@localhost:3306/budget_planner?charset=utf8mb4` | Database connection |
| `JWT_SECRET` | `change-this-secret` | Signs sign-in tokens. **Must be changed.** |
| `JWT_HOURS` | `8` | How long a sign-in lasts |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated frontend addresses allowed to call the API |

## How it works

### Data

- `fiscal_years`: one row per year. It also holds the overall expense limit and the rule for going over a limit (`block` or `warn`).
- `heads` and `lines`: these belong to a year. Monthly amounts are stored in columns `m1` (April) to `m12` (March), which makes reporting in SQL easy. Each head and line has a `code` that stays the same when a year is copied or planned. That code is how years are compared, and how a user's head access carries over to new years.
- `roles` holds permissions as JSON. `users` holds bcrypt-hashed passwords. `user_heads` lists the heads a restricted user may change.
- `activity_log` records every change. Repeated edits to the same line within 10 minutes are grouped into one entry.

### Permissions

Every permission is checked by the API, not just hidden in the screen.

| Group | Permissions |
|---|---|
| Budget data | view or edit expenses, view or edit income, add/rename/delete lines, add/rename/delete heads, view summary |
| Planning | plan next year, add and delete years, set budget limits |
| Files | import Excel, download Excel |
| Administration | view activity log, manage users and roles |

The standard roles are Administrator (everything, cannot be changed), Finance manager, Department editor and Viewer. A user can also be limited to particular heads. They can then change only those heads and see the rest as read-only. The API refuses to deactivate or delete the last active administrator.

### Budget limits

Limits can be set on the overall expense total and on any head. Each limit is either a fixed amount or a growth % over the previous year.

With the **block** rule, an entry that would take a head or the total over its limit is rejected (HTTP 409), and the user sees why. This applies to single edits, pasted rows and yearly spreads. With **warn**, the change is saved and a warning is returned. Lowering amounts is always allowed.

### Planning the next year (`services/planning.py`)

- Changes are set as an overall % for expenses and for income, which a head % overrides, which a line % overrides in turn.
- Every month of a line is scaled by the same factor, so the monthly pattern is kept.
- A **fixed head** is held at its base × (1 + head %). In automatic mode, lines without their own % absorb the difference. In manual mode the head must end at or below that amount before the year can be created.
- A **fixed total** works the same way. Heads that are neither fixed nor given their own % absorb the difference.
- Income lines with a quantity and a rate change by the student % (quantity) and the fee % (rate).
- Fixed amounts can be saved as limits in the new year.

## Tests

```bash
cd backend
pytest -q                                              # uses a temporary SQLite database
TEST_DATABASE_URL="mysql+pymysql://user:pass@localhost:3306/budget_test?charset=utf8mb4" pytest -q   # against MySQL
SAMPLE_XLSX=/path/to/Budget_26-27.xlsx pytest -q       # also imports your workbook
```

The tests cover sign-in and setup, editing and totals, quantity × rate spreading, planning with fixed heads and a fixed total (automatic and manual), limit blocking and warnings, restricted users, and Excel import and export.

## Before going live

- Set a long random `JWT_SECRET` and strong database passwords in `.env`.
- Put the app behind HTTPS (a reverse proxy such as nginx or Caddy with a certificate).
- Back up MySQL regularly, for example `mysqldump budget_planner > backup.sql` on a schedule.
- `create_all` only adds missing tables. For future changes to existing tables, add a migration tool such as Alembic.
