from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class Reading(Base):
    __tablename__ = "readings"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), primary_key=True)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    value: Mapped[float] = mapped_column(Float)
