import logging
import os

from flask import Flask

from app.config import Config, validate_config


def create_app():
    validate_config()

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    os.makedirs(app.instance_path, exist_ok=True)
    app.config["DATABASE_PATH"] = os.path.join(app.instance_path, "strava_tracker.db")

    logging.basicConfig(level=logging.INFO)

    from app import db

    db.init_db(app)

    from app.routes import bp

    app.register_blueprint(bp)

    return app
