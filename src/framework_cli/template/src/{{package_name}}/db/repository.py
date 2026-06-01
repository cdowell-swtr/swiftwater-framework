from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Item

# Hard cap on a single page so a caller can never request an unbounded read.
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50


def list_items(
    session: Session, *, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0
) -> list[Item]:
    """Return a bounded page of items (ordered by id).

    ``limit`` is clamped to ``[0, MAX_PAGE_SIZE]`` and ``offset`` floored at 0, so
    the read path stays bounded regardless of caller input — pass explicit
    limit/offset (or a cursor) to page through larger result sets.
    """
    bounded = max(0, min(limit, MAX_PAGE_SIZE))
    stmt = select(Item).order_by(Item.id).limit(bounded).offset(max(0, offset))
    return list(session.scalars(stmt))


def create_item(session: Session, name: str) -> Item:
    item = Item(name=name)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
