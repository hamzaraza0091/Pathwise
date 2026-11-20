import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.worker import run_backup

destination = run_backup()
if destination is None:
    sys.exit("Database file not found")
print(destination)
