from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from .models import Reading


def add_reading(
    session: Session, item_id: int, time: datetime, value: float
) -> Reading:
    row = Reading(item_id=item_id, time=time, value=value)
    session.add(row)
    session.commit()
    return row


def bucketed_averages(session: Session, bucket: str = "1 hour") -> Sequence[tuple]:
    """Average value per time bucket (TimescaleDB time_bucket), oldest first."""
    rows = session.execute(
        text(
            "SELECT time_bucket(CAST(:bucket AS interval), time) AS bucket, avg(value) AS avg "
            "FROM readings GROUP BY bucket ORDER BY bucket"
        ),
        {"bucket": bucket},
    )
    return [(r.bucket, float(r.avg)) for r in rows]
