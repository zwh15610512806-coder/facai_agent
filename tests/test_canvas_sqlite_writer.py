from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from services.canvas.sqlite_writer import begin_immediate_if_sqlite


class CanvasSqliteWriterTests(unittest.TestCase):
    def test_sqlite_acquires_immediate_writer_lease(self) -> None:
        db = Mock()
        db.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        begin_immediate_if_sqlite(db)

        statement = db.execute.call_args.args[0]
        self.assertEqual(str(statement), "BEGIN IMMEDIATE")

    def test_non_sqlite_keeps_native_transaction_behavior(self) -> None:
        db = Mock()
        db.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

        begin_immediate_if_sqlite(db)

        db.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
