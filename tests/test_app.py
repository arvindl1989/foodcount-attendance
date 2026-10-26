import random
import re
import shutil
from datetime import date, datetime

import pytest

from app import attendance, create_app
from app.db import get_db
from seed import seed

# Fixed "now": Tuesday 2026-10-27, 09:00 (before the 10:00 cutoff).
NOW = datetime(2026, 10, 27, 9, 0)


@pytest.fixture(scope="session")
def seeded_db(tmp_path_factory):
    """Seed once (password hashing is slow), then copy the file for each test."""
    path = tmp_path_factory.mktemp("template") / "seeded.sqlite3"
    app = create_app(DATABASE=str(path), SECRET_KEY="test")
    with app.app_context():
        seed(get_db(), rng=random.Random(1), reference_day=NOW.date())
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
    ("employee", "EMP001", "emp123", "/employee/"),
    ("manager", "MGR01", "manager123", "/manager/"),
    ("admin", "ADMIN01", "admin123", "/admin/"),
])
def test_login_redirects_to_dashboard(client, role, user, pw, dest):
    res = login(client, role, user, pw)
    assert res.status_code == 302 and res.headers["Location"] == dest
    assert client.get(dest).status_code == 200


def test_bad_password_and_wrong_portal(client):
    res = login(client, "employee", "EMP001", "nope")
    assert res.status_code == 200 and "Invalid employee ID or password" in res.get_data(as_text=True)
    res = login(client, "admin", "EMP001", "emp123")
    assert res.status_code == 200
    assert "doesn&#39;t have Admin access" in res.get_data(as_text=True)


def test_login_requires_csrf(client):
    res = client.post("/login/employee", data={"employee_id": "EMP001", "password": "emp123"})
    assert res.status_code == 400


def test_pages_require_login(client):
    for url in ("/employee/", "/manager/", "/admin/", "/admin/export.csv"):
        res = client.get(url)
        assert res.status_code == 302 and res.headers["Location"] == "/"
    assert client.get("/employee/api/entries?start=2026-10-01&end=2026-11-01").status_code == 401


def test_cross_role_access_blocked(client):
    login(client, "employee", "EMP001", "emp123")
    for url in ("/manager/", "/admin/"):
        res = client.get(url)
        assert res.status_code == 302 and res.headers["Location"] == "/"


def test_logout(client):
    login(client, "employee", "EMP001", "emp123")
    token = csrf(client, "/employee/")
    client.post("/logout", data={"csrf_token": token})
    assert client.get("/employee/").status_code == 302


def post_entry(client, day, status):
    token = csrf(client, "/employee/")
    return client.post("/employee/api/entries", json={"date": day, "status": status},
                       headers={"X-CSRF-Token": token})


def test_employee_set_and_clear(client):
    login(client, "employee", "EMP001", "emp123")
    assert post_entry(client, "2026-10-28", "WFH").status_code == 200
    assert post_entry(client, "2026-10-28", "LEAVE").status_code == 200  # update in place
    entries = client.get("/employee/api/entries?start=2026-10-28&end=2026-10-29").get_json()
    assert entries == [{"date": "2026-10-28", "status": "LEAVE"}]
    assert post_entry(client, "2026-10-28", "CLEAR").status_code == 200
    assert client.get("/employee/api/entries?start=2026-10-28&end=2026-10-29").get_json() == []


def test_employee_edit_rules(client, monkeypatch):
    login(client, "employee", "EMP001", "emp123")
    assert post_entry(client, "2026-10-26", "WFH").status_code == 422      # past
    assert post_entry(client, "2026-10-31", "WFH").status_code == 422      # Saturday
    assert post_entry(client, "2026-10-27", "WFH").status_code == 200      # today, before cutoff
    monkeypatch.setattr(attendance, "now", lambda: datetime(2026, 10, 27, 10, 0))
    res = post_entry(client, "2026-10-27", "CLEAR")                         # today, at cutoff
    assert res.status_code == 422 and "10:00" in res.get_json()["error"]
    assert post_entry(client, "2026-10-28", "BOGUS").status_code == 400


def test_api_without_csrf_rejected(client):
    login(client, "employee", "EMP001", "emp123")
    res = client.post("/employee/api/entries", json={"date": "2026-10-28", "status": "WFH"})
    assert res.status_code == 400


def test_manager_sees_only_direct_reports(client):
    login(client, "manager", "MGR01", "manager123")
    html = client.get("/manager/?month=2026-10").get_data(as_text=True)
    assert "EMP001" in html and "EMP004" in html  # team 0: EMP001, 004, 007...
    assert "EMP002" not in html and "EMP003" not in html
    assert "October 2026" in html
    assert "November 2026" in client.get("/manager/?month=2026-11").get_data(as_text=True)


def test_manager_status_filter(client, app):
    login(client, "manager", "MGR01", "manager123")
    only_leave = client.get("/manager/?month=2026-10&status=LEAVE").get_data(as_text=True)
    assert "cell-wfh" not in only_leave
    only_wfh = client.get("/manager/?month=2026-10&status=WFH").get_data(as_text=True)
    assert "cell-leave" not in only_wfh and "cell-wfh" in only_wfh


def test_admin_headcount_matches_formula(client, app):
    login(client, "admin", "ADMIN01", "admin123")
    with app.app_context():
        hc = attendance.headcount(date(2026, 10, 27))
        assert hc["total"] == 34
        assert hc["in_office"] == hc["total"] - hc["wfh"] - hc["leave"]
        assert sum(c["in_office"] for _, c in hc["by_location"]) == hc["in_office"]
        assert attendance.headcount(date(2026, 10, 31))["in_office"] == 0  # weekend
    html = client.get("/admin/?date=2026-10-27").get_data(as_text=True)
    assert f'<span class="stat-value">{hc["in_office"]}</span>' in html
    assert "Head Office" in html and "Engineering" in html


def test_admin_csv_export(client):
    login(client, "admin", "ADMIN01", "admin123")
    res = client.get("/admin/export.csv?date=2026-10-27")
    assert res.mimetype == "text/csv"
    lines = res.get_data(as_text=True).strip().splitlines()
    assert lines[0] == "date,employee_id,name,department,location,status"
    assert len(lines) == 35
    assert all(line.rsplit(",", 1)[1] in ("WFH", "LEAVE", "IN_OFFICE") for line in lines[1:])


def test_login_explains_empty_database(tmp_path):
    app = create_app(DATABASE=str(tmp_path / "empty.sqlite3"), SECRET_KEY="test", TESTING=True)
    client = app.test_client()
    html = login(client, "admin", "ADMIN01", "admin123").get_data(as_text=True)
    assert "No user accounts exist yet" in html
