import json
from pathlib import Path

from sqlalchemy.orm import Session

from .models import Item
from .repository import list_items


def seed(session: Session, seeds_path: Path) -> int:
    """Idempotently load items from a JSON file. Returns the number of rows inserted.

    A no-op (returns 0) if the table already has rows — safe to run on every startup.
    """
    if list_items(session):
        return 0
    rows = json.loads(Path(seeds_path).read_text())
    for row in rows:
        session.add(Item(name=row["name"]))
    session.commit()
    return len(rows)
