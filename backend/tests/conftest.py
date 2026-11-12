"""Shared test setup.

Nothing in the suite touches the network, a real MongoDB or a real page reader:

- MONGODB_URI is blanked before main.py loads the project's .env (load_dotenv
  never overrides a variable that is already set), and the API tests put an
  in-memory database in main.db.
- Every test runs with the reader's API keys removed from the environment and
  with httpx.AsyncClient.send refusing to run, so an accidental real call to
  the reading service (or any other outbound request) fails loudly.
- SUPERADMIN_* (which main.py's load_dotenv may have read from .env) are
  removed too, so no real super admin is ever seeded into a test database.

The plant workbook is not committed. Tests that need it skip when it is absent.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["MONGODB_URI"] = ""

from helpers import SKIP_REASON, WORKBOOK  # noqa: E402

READER_KEYS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")
SUPERADMIN_KEYS = ("SUPERADMIN_EMAIL", "SUPERADMIN_PASSWORD", "SUPERADMIN_NAME")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in READER_KEYS + SUPERADMIN_KEYS:
        monkeypatch.delenv(key, raising=False)

    async def refuse(self, request, *args, **kwargs):
        raise AssertionError(f"a test tried to reach the network: {request.method} {request.url}")

    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)


@pytest.fixture(scope="session")
def book() -> dict:
    """workbook_import.read_workbook() of the real plant workbook."""
    if not WORKBOOK.exists():
        pytest.skip(SKIP_REASON)
    import workbook_import

    return workbook_import.read_workbook(str(WORKBOOK))


@pytest.fixture(scope="session")
def cached():
    """The real workbook's cached values (as last calculated by Excel)."""
    if not WORKBOOK.exists():
        pytest.skip(SKIP_REASON)
    import openpyxl

    return openpyxl.load_workbook(WORKBOOK, data_only=True)
