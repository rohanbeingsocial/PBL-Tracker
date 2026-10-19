"""Settings come from environment variables. A local .env file is read if there is one."""
import os

from dotenv import load_dotenv

load_dotenv()


def require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


def optional(name: str) -> str:
    return os.environ.get(name, "").strip()
