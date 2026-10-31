"""Shared test configuration. Database fixtures live in tests/integration/conftest.py."""
import os

os.environ.setdefault("APP_ENV", "test")
# Tests never call real language models: a developer's backend/.env keys and Vertex project stay out.
for _name in ("GEMINI_API_KEY", "VERTEX_PROJECT", "VERTEX_ACCESS_TOKEN", "VERTEX_CREDENTIALS_FILE"):
    os.environ[_name] = ""
