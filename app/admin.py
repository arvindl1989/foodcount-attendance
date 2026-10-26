"""Admin portal: company headcount / food count."""
import csv
import io
from datetime import timedelta

from flask import Blueprint, Response, current_app, render_template, request

from . import attendance as att
from .auth import role_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _selected_day():
    return att.parse_iso_date(request.args.get("date"), default=att.today())


@bp.get("/")
@role_required("admin")
def dashboard():
    day = _selected_day()
    forecast = att.forecast(day, current_app.config["FORECAST_DAYS"])
    chart = {
        "labels": [f["date"].strftime("%a %d %b") for f in forecast],
        "in_office": [f["in_office"] for f in forecast],
        "closed": [f["closed"] for f in forecast],
    }
    return render_template(
        "admin/dashboard.html",
        day=day,
        today=att.today(),
        prev_day=(day - timedelta(days=1)).isoformat(),
        next_day=(day + timedelta(days=1)).isoformat(),
        summary=att.headcount(day),
        forecast=forecast,
        chart=chart,
    )


@bp.get("/export.csv")
@role_required("admin")
def export_csv():
    day = _selected_day()
    closed = att.is_weekend(day)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "employee_id", "name", "department", "location", "status"])
    for row in att.day_roster(day):
        status = row["status"] or ("OFFICE_CLOSED" if closed else "IN_OFFICE")
        writer.writerow([day.isoformat(), row["employee_id"], row["name"],
                         row["department"], row["location"], status])
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="food-count-{day.isoformat()}.csv"'},
    )
