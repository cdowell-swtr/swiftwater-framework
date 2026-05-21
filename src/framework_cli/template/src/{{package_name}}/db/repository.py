from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Item


def list_items(session: Session) -> list[Item]:
    return list(session.scalars(select(Item).order_by(Item.id)))


def create_item(session: Session, name: str) -> Item:
    item = Item(name=name)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
