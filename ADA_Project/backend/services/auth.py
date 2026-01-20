from typing import Optional

from models import db
from models.user import User
from . import bcrypt


def register_user(email: str, password: str) -> User:
    """
    Create a new user with the given email and password.
    Raises ValueError if email already exists or input is invalid.
    """
    email = (email or "").strip().lower()
    password = (password or "").strip()

    if not email or not password:
        raise ValueError("Email and password are required.")

    # Check if user already exists
    existing = User.query.filter_by(email=email).first()
    if existing:
        raise ValueError("A user with this email already exists.")

    # Hash the password
    pw_hash = bcrypt.generate_password_hash(password).decode("utf-8")

    # Create and save user
    user = User(email=email, password_hash=pw_hash)
    db.session.add(user)
    db.session.commit()
    return user


def authenticate_user(email: str, password: str) -> Optional[User]:
    """
    Check user credentials.
    Returns the User if email/password are correct, otherwise None.
    """
    email = (email or "").strip().lower()
    password = (password or "").strip()

    if not email or not password:
        return None

    user = User.query.filter_by(email=email).first()
    if not user:
        return None

    # Verify password
    if not bcrypt.check_password_hash(user.password_hash, password):
        return None

    return user
