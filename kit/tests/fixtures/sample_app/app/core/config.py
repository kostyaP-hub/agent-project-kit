import os

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
MAX_RETRIES = 3
