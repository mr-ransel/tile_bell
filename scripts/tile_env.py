"""Shared helper to load Tile credentials from .env or prompt."""

import os
import sys
from getpass import getpass
from pathlib import Path


def _load_dotenv():
    """Load .env file from the scripts directory if it exists."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value:
            os.environ.setdefault(key, value)


def get_credentials() -> tuple[str, str]:
    """Get Tile email and password from .env, environment, or interactive prompt."""
    _load_dotenv()

    email = os.environ.get("TILE_EMAIL", "").strip()
    password = os.environ.get("TILE_PASSWORD", "").strip()

    if not email:
        try:
            email = input("Tile account email: ").strip()
        except EOFError:
            print("Error: email is required")
            sys.exit(1)
    else:
        print(f"Using email from environment: {email}")

    if not email:
        print("Error: email is required")
        sys.exit(1)

    if not password:
        try:
            password = getpass("Tile account password: ")
        except EOFError:
            print("Error: password is required")
            sys.exit(1)
    else:
        print("Using password from environment")

    if not password:
        print("Error: password is required")
        sys.exit(1)

    return email, password
