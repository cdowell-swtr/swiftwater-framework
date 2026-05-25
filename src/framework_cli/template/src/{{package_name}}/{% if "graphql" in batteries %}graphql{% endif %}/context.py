from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from ..db.engine import get_session


def get_context(session: Annotated[Session, Depends(get_session)]) -> dict:
    """Strawberry context_getter — exposes a request-scoped DB session to resolvers."""
    return {"session": session}
