from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Embedding


def add_embedding(
    session: Session, item_id: int, embedding: Sequence[float]
) -> Embedding:
    row = Embedding(item_id=item_id, embedding=list(embedding))
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def nearest(session: Session, query: Sequence[float], k: int = 5) -> list[Embedding]:
    """The k nearest embeddings to `query` by cosine distance."""
    stmt = (
        select(Embedding)
        .order_by(Embedding.embedding.cosine_distance(list(query)))
        .limit(k)
    )
    return list(session.scalars(stmt))
