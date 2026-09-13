"""Compatibility runner for the Forward-OOS durability contract.

The old source-string checks assumed restore ran only on an empty directory,
which missed partial evidence loss. Execute the transaction/recovery regression
suite instead: its fixtures are isolated TEST ONLY SQLite data, not Postgres
integration tests or production observations.
"""
from pathlib import Path
import sys
import unittest

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromName(
        "fia.test_live_integrity_v673.StorageRecovery")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
