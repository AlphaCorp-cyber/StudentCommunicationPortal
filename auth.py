from functools import wraps
from flask import redirect, url_for, flash, session, request
from flask_login import LoginManager, current_user
from app import app
from models import User

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def require_login(f):
    """Decorator to require user to be logged in"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            session['next_url'] = request.url
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def require_role(required_role):
    """Decorator to require specific role"""
    def decorator(f):
        @wraps(f)
        @require_login
        def decorated_function(*args, **kwargs):
            if required_role == 'admin' and not (current_user.is_admin() or current_user.is_super_admin()):
                flash('Access denied. Admin privileges required.', 'error')
                return redirect(url_for('dashboard'))
            elif required_role == 'super_admin' and not current_user.is_super_admin():
                flash('Access denied. Super Admin privileges required.', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator