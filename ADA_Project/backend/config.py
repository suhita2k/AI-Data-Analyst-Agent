import os
from pathlib import Path

from dotenv import load_dotenv

# Base directory of the project (the "ada" folder)
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from .env (we will create it later from .env.example)
load_dotenv(BASE_DIR / ".env")


class Config:
    """Main configuration class for the ADA app."""

    # Flask basic config
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev_secret_key_change_me")
    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"

    # Database (SQLite by default)
    # If SQLALCHEMY_DATABASE_URI is not set, use instance/ada.db
    SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI") or (
        "sqlite:///" + str(BASE_DIR / "instance" / "ada.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = (
        os.getenv("SQLALCHEMY_TRACK_MODIFICATIONS", "False") == "True"
    )

    # File upload configuration
    MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "20"))
    MAX_CONTENT_LENGTH = MAX_FILE_MB * 1024 * 1024  # in bytes
    UPLOAD_FOLDER = str(BASE_DIR / "uploads")

    # AI / LLM provider settings
    ADA_LLM_PROVIDER = os.getenv("ADA_LLM_PROVIDER", "gemini").lower()
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None

    # CORS / allowed origins
    # Example: "http://127.0.0.1:5000,http://localhost:5000"
    ALLOWED_ORIGINS = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]


# Optional: you can define other configs later (Production, Testing, etc.)
class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False

