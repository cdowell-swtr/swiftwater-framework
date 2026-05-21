from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..db.engine import get_session
from ..db.models import Item
from ..db.repository import list_items

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


class ItemRead(BaseModel):
    """Response schema — the contract the API exposes (decoupled from the ORM model)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


@router.get("/items", response_model=list[ItemRead])
def get_items(session: SessionDep) -> list[Item]:
    """List seeded/created items — demonstrates the DB wiring end to end.

    FastAPI serializes the ORM objects through ItemRead (the response contract).
    """
    return list_items(session)
