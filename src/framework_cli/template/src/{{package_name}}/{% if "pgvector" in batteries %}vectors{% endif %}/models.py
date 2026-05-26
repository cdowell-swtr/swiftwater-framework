from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base

_DIM = 1536


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    embedding: Mapped[list[float]] = mapped_column(Vector(_DIM))
