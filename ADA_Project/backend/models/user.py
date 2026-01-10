from flask_login import UserMixin
from datetime import datetime

from . import db  # import the db object from models/__init__.py


class User(UserMixin, db.Model):
    """User model for authentication (register / login)."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    # we'll use email as the unique login field
    email = db.Column(db.String(255), unique=True, nullable=False)

    # store only the password hash, never the plain text password
    password_hash = db.Column(db.String(255), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<User {self.email}>"
    