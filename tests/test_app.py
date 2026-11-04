import random
import re
import shutil
from datetime import date, datetime

import pytest

from app import attendance, create_app
from app.db import get_db
from seed import add_sample_entries, read_roster, sync_roster

# Fixed "now": Tuesday 2026-10-27, 09:00 (before the 10:00 cutoff).
NOW = datetime(2026, 10, 27, 9, 0)

# From data/roster.csv
EMP = "40103405"     # BALAJI K, Internal Controls, reports to Anand Shanbag
MGR = "64120538"     # Anand Shanbag
ADMIN = "64061732"   # SATHISH KUMAR M
TOTAL = 26           # 21 employees + 4 managers + 1 admin
PW = "1234"


@pytest.fixture(scope="session")
def seeded_db(tmp_path_factory):
    """Seed once (password hashing is slow), then copy the file for each test."""
    path = tmp_path_factory.mktemp("template") / "seeded.sqlite3"
    app = create_app(DATABASE=str(path), SECRET_KEY="test")
    with app.app_context():
        db = get_db()
        sync_roster(db, read_roster(app.config["ROSTER_FILE"]))
        add_sample_entries(db, rng=random.Random(1), reference_day=NOW.date())
    return path


@pytest.fixture
def app(tmp_path, monkeypatch, seeded_db):
    monkeypatch.setattr(attendance, "now", lambda: NOW)
    db_path = tmp_path / "test.sqlite3"
    shutil.copy(seeded_db, db_path)
    return create_app(DATABASE=str(db_path), SECRET_KEY="test", TESTING=True)


@pytest.fixture
def client(app):
    return app.test_client()


def csrf(client, url="/"):
    html = client.get(url).get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def login(client, role, employee_id, password):
    token = csrf(client, f"/login/{role}")
    return client.post(f"/login/{role}", data={
        "employee_id": employee_id, "password": password, "csrf_token": token,
    })


def test_home_has_three_portals(client):
    html = client.get("/").get_data(as_text=True)
    for role in ("employee", "manager", "admin"):
        assert f'href="/login/{role}"' in html


@pytest.mark.parametrize("role,user,pw,dest", [
    ("employee", EMP, PW, "/employee/"),
    ("manager", MGR, PW, "/manager/"),
    ("admin", ADMIN, PW, "/admin/"),
])
def test_login_redirects_to_dashboard(client, role, user, pw, dest):
    res = login(client, role, user, pw)
    assert res.status_code == 302 and res.headers["Location"] == dest
    assert client.get(dest).status_code == 200


def test_bad_password_and_wrong_portal(client):
    res = login(client, "employee", EMP, "nope")
    assert res.status_code == 200 and "Invalid employee ID or password" in res.get_data(as_text=True)
    res = login(client, "admin", EMP, PW)
    assert res.status_code == 200
    assert "doesn&#39;t have Admin access" in res.get_data(as_text=True)


def test_login_requires_csrf(client):
    res = client.post("/login/employee", data={"employee_id": EMP, "password": PW})
    assert res.status_code == 400


def test_pages_require_login(client):
    for url in ("/employee/", "/manager/", "/admin/", "/admin/export.csv"):
        res = client.get(url)
        assert res.status_code == 302 and res.headers["Location"] == "/"
    assert client.get("/employee/api/entries?start=2026-10-01&end=2026-11-01").status_code == 401


def test_cross_role_access_blocked(client):
    login(client, "employee", EMP, PW)
    for url in ("/manager/", "/admin/"):
        res = client.get(url)
        assert res.status_code == 302 and res.headers["Location"] == "/"


def test_logout(client):
    login(client, "employee", EMP, PW)
    token = csrf(client, "/employee/")
    client.post("/logout", data={"csrf_token": token})
    assert client.get("/employee/").status_code == 302


def post_entry(client, day, status):
    token = csrf(client, "/employee/")
    return client.post("/employee/api/entries", json={"date": day, "status": status},
                       headers={"X-CSRF-Token": token})


def test_employee_set_and_clear(client):
    login(client, "employee", EMP, PW)
    assert post_entry(client, "2026-10-28", "WFH").status_code == 200
    assert post_entry(client, "2026-10-28", "LEAVE").status_code == 200  # update in place
    entries = client.get("/employee/api/entries?start=2026-10-28&end=2026-10-29").get_json()
    assert entries == [{"date": "2026-10-28", "status": "LEAVE"}]
    assert post_entry(client, "2026-10-28", "CLEAR").status_code == 200
    assert client.get("/employee/api/entries?start=2026-10-28&end=2026-10-29").get_json() == []


def test_employee_edit_rules(client, monkeypatch):
    login(client, "employee", EMP, PW)
    assert post_entry(client, "2026-10-26", "WFH").status_code == 422      # past
    assert post_entry(client, "2026-10-31", "WFH").status_code == 422      # Saturday
    assert post_entry(client, "2026-10-27", "WFH").status_code == 200      # today, before cutoff
    monkeypatch.setattr(attendance, "now", lambda: datetime(2026, 10, 27, 10, 0))
    res = post_entry(client, "2026-10-27", "CLEAR")                         # today, at cutoff
    assert res.status_code == 422 and "10:00" in res.get_json()["error"]
    assert post_entry(client, "2026-10-28", "BOGUS").status_code == 400


def test_api_without_csrf_rejected(client):
    login(client, "employee", EMP, PW)
    res = client.post("/employee/api/entries", json={"date": "2026-10-28", "status": "WFH"})
    assert res.status_code == 400


def test_manager_sees_only_direct_reports(client):
    login(client, "manager", MGR, PW)
    html = client.get("/manager/?month=2026-10").get_data(as_text=True)
    for member in ("40103405", "40105266", "64127077", "40104868"):  # Internal Controls
        assert member in html
    assert "64166189" not in html and "64131777" not in html  # other teams
    assert "4 direct reports" in html
    assert "October 2026" in html
    assert "November 2026" in client.get("/manager/?month=2026-11").get_data(as_text=True)


def test_manager_status_filter(client, app):
    login(client, "manager", MGR, PW)
    only_leave = client.get("/manager/?month=2026-10&status=LEAVE").get_data(as_text=True)
    assert "cell-wfh" not in only_leave
    only_wfh = client.get("/manager/?month=2026-10&status=WFH").get_data(as_text=True)
    assert "cell-leave" not in only_wfh and "cell-wfh" in only_wfh


def test_admin_headcount_matches_formula(client, app):
    login(client, "admin", ADMIN, PW)
    with app.app_context():
        hc = attendance.headcount(date(2026, 10, 27))
        assert hc["total"] == TOTAL
        assert hc["in_office"] == hc["total"] - hc["wfh"] - hc["leave"]
        assert sum(c["in_office"] for _, c in hc["by_department"]) == hc["in_office"]
        assert hc["bus_pass"] == 10
        assert sum(c["bus"] for _, c in hc["by_department"]) == hc["bus"]
        assert attendance.headcount(date(2026, 10, 31))["in_office"] == 0  # weekend
    html = client.get("/admin/?date=2026-10-27").get_data(as_text=True)
    assert f'<span class="stat-value">{hc["in_office"]}</span>' in html
    assert "Internal Controls" in html and "Marketing Hub" in html and "STP" in html


def test_admin_csv_export(client):
    login(client, "admin", ADMIN, PW)
    res = client.get("/admin/export.csv?date=2026-10-27")
    assert res.mimetype == "text/csv"
    lines = res.get_data(as_text=True).strip().splitlines()
    assert lines[0] == "date,employee_id,name,department,location,status,bus_pass,food_count,bus_count"
    assert len(lines) == TOTAL + 1
    rows = [line.split(",") for line in lines[1:]]
    assert all(r[5] in ("WFH", "LEAVE", "IN_OFFICE") for r in rows)
    assert sum(r[6] == "yes" for r in rows) == 10
    for r in rows:  # BC only for pass holders who are in office
        assert r[8] == str(int(r[5] == "IN_OFFICE" and r[6] == "yes"))


def test_login_explains_empty_database(tmp_path):
    app = create_app(DATABASE=str(tmp_path / "empty.sqlite3"), SECRET_KEY="test", TESTING=True)
    client = app.test_client()
    html = login(client, "admin", ADMIN, PW).get_data(as_text=True)
    assert "No user accounts exist yet" in html


def write_roster(path, text):
    path.write_text("employee_id,name,role,manager,department,location\n" + text)
    return path


def test_roster_sync_updates_and_removes(app, tmp_path):
    with app.app_context():
        db = get_db()
        # Simulate the employee having changed their password.
        db.execute("UPDATE users SET password_hash = 'kept' WHERE employee_id = ?", (EMP,))
        roster = write_roster(tmp_path / "r.csv",
            f"{MGR},Anand Shanbag,manager,,Internal Controls,Chennai\n"
            f"{EMP},Balaji K,employee,anand  SHANBAG,Internal Controls,Chennai\n"
            "99999999,NEW PERSON,employee,Anand Shanbag,Internal Controls,\n")
        assert sync_roster(db, read_roster(roster)) == (1, 2, TOTAL - 2)
        rows = {r["employee_id"]: r for r in db.execute("SELECT * FROM users")}
        assert set(rows) == {MGR, EMP, "99999999"}
        assert rows[EMP]["name"] == "Balaji K" and rows[EMP]["location"] == "Chennai"
        assert rows[EMP]["password_hash"] == "kept"
        assert rows["99999999"]["manager_id"] == rows[MGR]["id"]
        assert db.execute("SELECT COUNT(*) FROM attendance_entries a JOIN users u ON u.id = a.user_id "
                          "WHERE u.employee_id NOT IN (?, ?, '99999999')", (MGR, EMP)).fetchone()[0] == 0


def test_roster_rejects_unknown_manager(tmp_path):
    roster = write_roster(tmp_path / "r.csv", "1,A,employee,NOBODY,X,\n")
    with pytest.raises(ValueError, match="NOBODY"):
        read_roster(roster)


def test_change_password(client):
    login(client, "employee", EMP, PW)
    token = csrf(client, "/account/password")
    form = {"current_password": PW, "new_password": "short", "confirm_password": "short", "csrf_token": token}
    assert "at least 8" in client.post("/account/password", data=form).get_data(as_text=True)
    form.update(new_password="better-pass-1", confirm_password="better-pass-1")
    assert client.post("/account/password", data=form).status_code == 302
    client.post("/logout", data={"csrf_token": csrf(client, "/employee/")})
    assert login(client, "employee", EMP, PW).status_code == 200        # old password fails
    assert login(client, "employee", EMP, "better-pass-1").status_code == 302


def test_ritu_manages_the_admin(client):
    login(client, "manager", "11223344", PW)
    html = client.get("/manager/").get_data(as_text=True)
    assert "SATHISH KUMAR M" in html and "1 direct report" in html


def test_bus_count_is_pass_holders_in_office(app):
    with app.app_context():
        db = get_db()
        holders = [r["id"] for r in db.execute("SELECT id FROM users WHERE bus_pass = 1 ORDER BY id")]
        day = date(2026, 10, 28)
        db.execute("DELETE FROM attendance_entries WHERE date = ?", (day.isoformat(),))
        attendance.set_status(holders[0], day, "WFH")
        attendance.set_status(holders[1], day, "LEAVE")
        hc = attendance.headcount(day)
        assert hc["in_office"] == TOTAL - 2
        assert hc["bus"] == len(holders) - 2
        assert attendance.headcount(date(2026, 10, 31))["bus"] == 0  # weekend


def test_manager_grid_shows_fc_and_bc_tags(client):
    login(client, "manager", "40104978", PW)  # Rajesh P: STP, 7 bus pass holders
    html = client.get("/manager/").get_data(as_text=True)
    assert html.count('class="tag tag-fc"') == 12 + 1   # every report + legend
    assert html.count('class="tag tag-bc"') == 7 + 1


def test_old_database_gets_bus_pass_column(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL,
                    manager_id INTEGER, department TEXT, location TEXT)""")
    conn.execute("INSERT INTO users (employee_id, name, password_hash, role) VALUES ('1', 'A', 'x', 'employee')")
    conn.commit()
    conn.close()
    create_app(DATABASE=str(path), SECRET_KEY="test")
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT bus_pass FROM users").fetchall() == [(0,)]
