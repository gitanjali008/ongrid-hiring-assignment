import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev")
    # Credentials are URL-encoded so passwords containing @, :, / or # don't break the URI.
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{quote_plus(os.getenv('MYSQL_USER', 'root'))}:"
        f"{quote_plus(os.getenv('MYSQL_PASSWORD', ''))}@"
        f"{os.getenv('MYSQL_HOST', '127.0.0.1')}:"
        f"{os.getenv('MYSQL_PORT', '3306')}/"
        f"{os.getenv('MYSQL_DATABASE', 'expense_tracker')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
