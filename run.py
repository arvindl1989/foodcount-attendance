"""Start the development server.

    python run.py

Creates the SQLite database on first run and fills it with demo data if it's
empty. HOST / PORT / FLASK_DEBUG environment variables are honoured.
"""
import os

from app import create_app
from seed import seed_if_empty

app = create_app()

if __name__ == "__main__":
    if seed_if_empty(app):
        print("First run: demo data created (see README for logins).")
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    app.run(host=host, port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
