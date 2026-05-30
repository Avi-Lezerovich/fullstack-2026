"""Flask application factory."""
import os

from flask import Flask
from flask_cors import CORS

from .models import init_db, UPLOAD_DIR
from .routes import api


def create_app() -> Flask:
    app = Flask(__name__)
    # Credentialed CORS (cookies) can't use "*" — list the dev client origins explicitly.
    CORS(
        app,
        supports_credentials=True,
        resources={r"/api/*": {"origins": [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]}},
    )
    os.makedirs(UPLOAD_DIR, exist_ok=True)   # ensure the image upload folder exists
    init_db()            # create schema + seed on first run
    app.register_blueprint(api)
    return app
