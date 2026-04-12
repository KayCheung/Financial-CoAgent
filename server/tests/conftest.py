from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


# Ensure `from app...` imports work when running `pytest` from server root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Force tests to use an isolated writable sqlite file.
TMP_DIR = Path(tempfile.gettempdir()) / "financial-coagent-tests"
TMP_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(TMP_DIR / 'coagent-test.db').as_posix()}")
AUDIT_WAL_DIR = TMP_DIR / "audit-wal"
AUDIT_WAL_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("AUDIT_WAL_DIR", str(AUDIT_WAL_DIR))
