from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..db.engine import get_session
from ..db.models import Item
from ..db.repository import MAX_PAGE_SIZE, list_items

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


class ItemRead(BaseModel):
    """Response schema — the contract the API exposes (decoupled from the ORM model)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


@router.get("/items", response_model=list[ItemRead])
def get_items(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Item]:
    """List seeded/created items (paginated) — demonstrates the DB wiring end to end.

    The result set is always bounded: ``limit`` is capped at MAX_PAGE_SIZE and the
    repository clamps it. FastAPI serializes the ORM objects through ItemRead.
    """
    return list_items(session, limit=limit, offset=offset)
