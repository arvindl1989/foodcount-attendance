"""Start the development server.

    python run.py

Creates the SQLite database on first run, loads the users from
data/roster.csv and, if there are no entries yet, adds sample WFH / leave
entries so the dashboards have something to show. HOST / PORT / FLASK_DEBUG
environment variables are honoured.
"""
import os

from app import create_app
from seed import setup_data

app = create_app()

if __name__ == "__main__":
    setup_data(app, sample_entries=True)
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
