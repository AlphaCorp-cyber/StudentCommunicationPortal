import os
from dotenv import load_dotenv

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
import logging

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET") or os.urandom(32)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
    "connect_args": {
        "connect_timeout": 10,
        "application_name": "drivelink_app"
    }
}

# Configure file uploads
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'doc', 'docx'}

# Initialize the app with the extension
db.init_app(app)

def create_tables():
    """Create database tables with proper error handling"""
    try:
        with app.app_context():
            # Make sure to import the models here or their tables won't be created
            import models  # noqa: F401
            db.create_all()
            logging.info("Database tables created successfully")
            return True
    except Exception as e:
        logging.error(f"Failed to create database tables: {e}")
        return False

def init_app_with_routes():
    """Initialize app with routes after database setup"""
    try:
        # Import routes after app is set up
        import routes  # noqa: F401
        import auth  # noqa: F401
        
        # Register subscription blueprint
        from subscription_routes import subscription_bp
        app.register_blueprint(subscription_bp)
        
        # Register onboarding blueprint
        from onboarding_routes import onboarding_bp
        app.register_blueprint(onboarding_bp)
        
        logging.info("DriveLink initialized successfully")
        return True
    except Exception as e:
        logging.error(f"Failed to initialize routes: {e}")
        return False

# Try to create tables and initialize routes
if __name__ != "__main__":
    # This ensures tables are created when the app is imported by gunicorn
    try:
        if create_tables():
            init_app_with_routes()
        else:
            logging.warning("Database unavailable, but starting app anyway")
            init_app_with_routes()
    except Exception as e:
        logging.error(f"App initialization error: {e}")
        # Start the app even if database initialization fails
        init_app_with_routes()
