"""Shared opt-in marker for destructive PostgreSQL integration tests."""
from __future__ import annotations

import os
import unittest

requires_disposable_postgres = unittest.skipUnless(
    bool(os.environ.get("FACAI_TEST_DATABASE_URL", "").strip()),
    "requires FACAI_TEST_DATABASE_URL for a disposable PostgreSQL test database",
)
