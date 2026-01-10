from flask_sqlalchemy import SQLAlchemy

# Main SQLAlchemy database object for the whole app.
# It will be initialized with the Flask app in app.py.
db = SQLAlchemy()