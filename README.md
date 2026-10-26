# WFH & Food Count

A small web app where employees mark the days they work from home or are on
leave, managers see where their team is, and admins get a daily
**expected in-office headcount** so the kitchen knows how much food to prepare.

Python + Flask, SQLite, server-rendered Jinja templates, plain CSS and a little
vanilla JS. No build step.

![Home](docs/screenshots/home.png)

## Quick start

```sh
./start.sh
```

That creates a virtualenv in `.venv`, installs the requirements and starts the
server on <http://127.0.0.1:5000>. On first run the SQLite database
(`instance/foodcount.sqlite3`) is created and filled with demo data.

Manual steps (also works on Windows):

```sh
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

To throw away all data and generate fresh demo data:

```sh
python seed.py --reset
```

The calendar (FullCalendar) and chart (Chart.js) are loaded from the jsDelivr
CDN, so the browser needs internet access.

## Deploy to Railway

The repo is ready for [Railway](https://railway.com): `railway.json` starts the
app with gunicorn (`wsgi.py`), which listens on the `PORT` Railway provides.

1. **Create the service.** In Railway: *New Project → Deploy from GitHub repo*,
   pick this repository. Under the service's *Settings → Source*, choose the
   branch to deploy.
2. **Add a volume** to the service with mount path `/data`. Without it the
   SQLite database is wiped on every deploy.
3. **Set variables** (service → *Variables*):

   | Variable | Value | Why |
   |----------|-------|-----|
   | `DATABASE` | `/data/foodcount.sqlite3` | keep the database on the volume |
   | `APP_TIMEZONE` | your zone, e.g. `Asia/Kolkata` | Railway runs on UTC; this sets "today" and the 10:00 cutoff |
   | `SESSION_COOKIE_SECURE` | `1` | Railway serves HTTPS |
   | `SEED_DEMO_DATA` | `1` | optional: load demo users if the database is empty |
   | `CUTOFF_HOUR` | e.g. `10` | optional |

   `SECRET_KEY` is optional: if unset, one is generated and stored on the
   volume next to the database.
4. **Expose it:** *Settings → Networking → Generate Domain*.

Run one replica only: a SQLite file on a volume can't be shared between
replicas. Two gunicorn workers in that one replica is fine for this load.

> **Heads-up:** with `SEED_DEMO_DATA=1`, anyone who has the URL can log in with
> the demo passwords listed below, including as admin. That's fine for showing
> the prototype around. Don't put real employee data in until there's a way to
> manage users and passwords.

## Demo logins

| Role     | Employee ID          | Password     |
|----------|----------------------|--------------|
| Admin    | `ADMIN01`            | `admin123`   |
| Manager  | `MGR01`, `MGR02`, `MGR03` | `manager123` |
| Employee | `EMP001` – `EMP030`  | `emp123`     |

Seed data: 1 admin, 3 managers, 30 employees (10 per manager) across
2 locations (Head Office, City Centre) and 3 departments (Engineering, Finance,
Operations), with random WFH and leave entries for the current and next month.

## The portals

The home page has one button per role. Each goes to that role's login page;
after login you land on your dashboard. Every page checks the role, so an
employee can't open the manager or admin pages (and logged-out visitors are
sent back to the home page).

### Employee: my calendar

![Employee calendar](docs/screenshots/employee.png)

- Month calendar of your own entries. Click a weekday and choose
  **Work from home**, **Leave** or **Clear** (back to in office).
- Blue = WFH, orange = leave, no colour = in office. Weekends are greyed out.
- Past dates can't be edited, and today is locked from the cutoff time
  (`CUTOFF_HOUR`, default 10:00). The server enforces these rules, not only the UI.
- Side panel: WFH, leave and office days for the month you're viewing.

### Manager: team summary

![Manager team grid](docs/screenshots/manager.png)

- Only your direct reports.
- "Today" panel: who's working from home or on leave today.
- Month grid: people as rows, days as columns, same colours. Previous / next
  month navigation.
- Filter: all, WFH only or leave only. The per-person WFH / leave totals always
  cover the whole month.

### Admin: food count

![Admin dashboard](docs/screenshots/admin.png)

- Today's numbers by default: total employees, WFH, leave and
  **expected in office = total − WFH − leave**.
- Date picker (plus previous / next day) to look at any date.
- Breakdown by location and by department.
- 7-day forward view as a table and bar chart. Weekends show as office closed.
- **Export CSV** for the selected date: employee ID, name, department, location
  and status (`WFH`, `LEAVE`, `IN_OFFICE`).

## Configuration

Settings live in `app/config.py`. Each one can be overridden with an
environment variable of the same name.

| Setting          | Default                        | Meaning |
|------------------|--------------------------------|---------|
| `CUTOFF_HOUR`, `CUTOFF_MINUTE` | `10`, `0`        | Time after which today's status is locked |
| `APP_TIMEZONE`   | server local time              | IANA zone for "today" and the cutoff, e.g. `Asia/Kolkata` |
| `DATABASE`       | `instance/foodcount.sqlite3`   | SQLite file path |
| `SECRET_KEY`     | random, saved as `secret_key` next to the database | Session signing key |
| `HEADCOUNT_ROLES`| employee, manager, admin       | Which roles count towards the food count |
| `SESSION_COOKIE_SECURE` | off                | Set to `1` when served over HTTPS |
| `SEED_DEMO_DATA` | off                            | `1` = `wsgi.py` seeds an empty database on start |
| `HOST`, `PORT`, `FLASK_DEBUG` | `127.0.0.1`, `5000`, off | Dev server options (read by `run.py`; gunicorn reads `PORT`) |

## Project layout

```
run.py               start the dev server (creates + seeds the DB on first run)
wsgi.py              production entry point for gunicorn (used on Railway)
railway.json         Railway start command and health check
seed.py              demo data; `python seed.py --reset` to regenerate
start.sh             one-command setup + run
app/
  __init__.py        application factory
  config.py          settings
  schema.sql         tables: users, attendance_entries
  db.py              SQLite connection per request
  attendance.py      business rules: edit cutoff, headcount, forecast
  auth.py            home, login/logout, role guard, CSRF
  employee.py        employee calendar + JSON API
  manager.py         manager team grid
  admin.py           admin dashboard + CSV export
  templates/         Jinja templates (base, home, login, one folder per role)
  static/            style.css, app.js, employee.js, admin.js
tests/test_app.py    pytest suite
```

### Data model

- **users**: `id`, `employee_id` (unique, the username), `name`,
  `password_hash` (werkzeug), `role` (employee / manager / admin),
  `manager_id` → users, `department`, `location`
- **attendance_entries**: `id`, `user_id`, `date`, `status` (WFH / LEAVE),
  `created_at`, `updated_at`, unique on `(user_id, date)`.
  No row means in office.

## Tests

```sh
pip install -r requirements-dev.txt
python -m pytest
```

The suite covers login and logout, cross-role blocking, CSRF, the employee
edit rules (past, weekend, cutoff), the manager's team scoping and filter,
the food-count formula and the CSV export.

## Notes and next steps

- Out of scope for this prototype, with room left for them in the design:
  approval workflows (add an approval state column to `attendance_entries`),
  email notifications, SSO (replace the login view in `auth.py`), recurring
  WFH patterns, and public holidays (extend `attendance.is_weekend` /
  `edit_block_reason` and `headcount`).
- Managers and the admin count towards the headcount but don't have their own
  calendar yet, so they always count as in office.
- `run.py` uses Flask's development server; for hosting use gunicorn via
  `wsgi.py` (see *Deploy to Railway*).
