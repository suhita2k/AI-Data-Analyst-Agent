from flask_bcrypt import Bcrypt
from flask_login import LoginManager

from models import db
from models.user import User

# Bcrypt for password hashing
bcrypt = Bcrypt()

# Login manager for Flask-Login
login_manager = LoginManager()
login_manager.login_view = "login"  # endpoint name we will create later
login_manager.login_message_category = "info"


@login_manager.user_loader
def load_user(user_id: str):
    """Tell Flask-Login how to load a user from the database."""
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None