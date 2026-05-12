import os

MONGODB_CONNECTION_STRING = os.getenv("MONGODB_CONNECTION_STRING") or os.getenv("MONGODB_URL", "")
MONGODB_DATABASE_PREFIX = os.getenv("MONGODB_DATABASE_PREFIX") or os.getenv("MONGODB_DATABASE", "")


def has_mongodb_config() -> bool:
    return bool(MONGODB_CONNECTION_STRING)
