"""Home page, login/logout, role guard and CSRF protection."""
import secrets
from functools import wraps

from flask import (
    Blueprint, abort, flash, g, jsonify, redirect, render_template, request,
    session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)

# Role -> how it appears in the UI and where its dashboard lives.
ROLES = {
    "employee": {
        "label": "Employee",
        "endpoint": "employee.calendar",
        "blurb": "Mark the days you're working from home or on leave.",
    },
    "manager": {
        "label": "Manager",
        "endpoint": "manager.team",
        "blurb": "See where your team is working this month.",
    },
    "admin": {
        "label": "Admin",
        "endpoint": "admin.dashboard",
        "blurb": "Company headcount and daily food count.",
    },
}


def init_app(app):
    app.before_request(load_logged_in_user)
    app.before_request(check_csrf)
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.context_processor
    def inject_roles():
        return {"ROLES": ROLES}


def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if g.user is None:  # user was deleted (e.g. database re-seeded)
            session.clear()


def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def check_csrf():
    """Reject state-changing requests without the session's CSRF token.

    Forms send it as a hidden `csrf_token` field, fetch() calls as an
    X-CSRF-Token header.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    expected = session.get("_csrf", "")
    if not expected or not secrets.compare_digest(sent, expected):
        abort(400, description="Your session has expired. Please reload the page and try again.")


def role_required(role, api=False):
    """Only let logged-in users with `role` through.

    Pages redirect to the home page; API endpoints (api=True) answer with a
    JSON error instead so the front end can react.
    """
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                if api:
                    return jsonify(error="Not logged in."), 401
                flash("Please log in to continue.", "info")
                return redirect(url_for("auth.home"))
            if g.user["role"] != role:
                if api:
                    return jsonify(error="Not allowed."), 403
                flash("You don't have access to that page.", "error")
                return redirect(url_for("auth.home"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


@bp.get("/")
def home():
    return render_template("home.html")


@bp.route("/login/<role>", methods=["GET", "POST"])
def login(role):
    if role not in ROLES:
        abort(404)
    info = ROLES[role]

    if g.user is not None and g.user["role"] == role:
        return redirect(url_for(info["endpoint"]))

    error = None
    employee_id = ""
    if request.method == "POST":
        employee_id = request.form.get("employee_id", "").strip().upper()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE employee_id = ?", (employee_id,)
        ).fetchone()

        if user is None and not get_db().execute("SELECT 1 FROM users LIMIT 1").fetchone():
            error = ("No user accounts exist yet. Add people to data/roster.csv "
                     "and restart (or run `python seed.py`).")
        elif user is None or not check_password_hash(user["password_hash"], password):
            error = "Invalid employee ID or password."
        elif user["role"] != role:
            error = (f"This account doesn't have {info['label']} access. "
                     f"Please use the {ROLES[user['role']]['label']} login.")
        else:
            session.clear()  # fresh session on login
            session.permanent = True
            session["user_id"] = user["id"]
            return redirect(url_for(info["endpoint"]))

    return render_template("login.html", role=role, info=info, error=error,
                           employee_id=employee_id)


MIN_PASSWORD_LENGTH = 8


@bp.route("/account/password", methods=["GET", "POST"])
def change_password():
    if g.user is None:
        flash("Please log in to continue.", "info")
        return redirect(url_for("auth.home"))

    error = None
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        if not check_password_hash(g.user["password_hash"], current):
            error = "Your current password is incorrect."
        elif len(new) < MIN_PASSWORD_LENGTH:
            error = f"The new password must be at least {MIN_PASSWORD_LENGTH} characters."
        elif new != request.form.get("confirm_password", ""):
            error = "The new passwords don't match."
        elif new == current:
            error = "The new password must be different from the current one."
        else:
            db = get_db()
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                       (generate_password_hash(new), g.user["id"]))
            db.commit()
            flash("Your password has been changed.", "info")
            return redirect(url_for(ROLES[g.user["role"]]["endpoint"]))

    return render_template("change_password.html", error=error, min_length=MIN_PASSWORD_LENGTH)


@bp.post("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.home"))
