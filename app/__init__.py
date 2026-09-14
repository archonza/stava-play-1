import logging

from flask import Flask

from app.config import Config, validate_config


def create_app():
    validate_config()

    app = Flask(__name__)
    app.config.from_object(Config)

    logging.basicConfig(level=logging.INFO)

    from app import db

    db.init_db(app)

    from app.routes import bp

    app.register_blueprint(bp)

    return app
