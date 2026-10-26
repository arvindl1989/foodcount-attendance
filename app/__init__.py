"""WFH & Food Count — Flask application factory."""
import os
import secrets

from flask import Flask

from .config import Config


def create_app(config_object=Config, **overrides):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)
    app.config.update(overrides)

    os.makedirs(app.instance_path, exist_ok=True)
    if not app.config.get("DATABASE"):
        app.config["DATABASE"] = os.path.join(app.instance_path, "foodcount.sqlite3")
    data_dir = os.path.dirname(os.path.abspath(app.config["DATABASE"]))
    os.makedirs(data_dir, exist_ok=True)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _load_or_create_secret(data_dir)

    from . import admin, auth, db, employee, manager

    db.init_app(app)
    auth.init_app(app)

    app.register_blueprint(auth.bp)
    app.register_blueprint(employee.bp)
    app.register_blueprint(manager.bp)
    app.register_blueprint(admin.bp)
    return app


def _load_or_create_secret(directory):
    path = os.path.join(directory, "secret_key")
    if os.path.exists(path):
        with open(path) as fh:
            return fh.read().strip()
    key = secrets.token_hex(32)
    with open(path, "w") as fh:
        fh.write(key)
    return key
