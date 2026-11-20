import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings

if len(sys.argv) != 2:
    sys.exit("usage: python scripts/restore.py <backup-file>  (stop the API server first)")

backup = Path(sys.argv[1])
try:
    connection = sqlite3.connect(backup)
    result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    connection.close()
except sqlite3.DatabaseError as exc:
    sys.exit(f"{backup} is not a valid SQLite database: {exc}")
if result != "ok":
    sys.exit(f"Backup failed integrity check: {result}")

target = Path(settings.database_url.replace("sqlite:///", ""))
if target.exists():
    shutil.copy2(target, target.with_suffix(".pre-restore.db"))
for suffix in ("-wal", "-shm"):
    Path(str(target) + suffix).unlink(missing_ok=True)
shutil.copy2(backup, target)
print(f"Restored {backup} to {target}")
