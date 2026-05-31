import re

from sqlalchemy import text
from sqlalchemy.orm import Session

_GRAPH = "app_graph"

# Relationship types are not quoted in Cypher, so they can't be escaped — constrain
# them to a bare identifier instead.
_REL_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _escape_literal(value: str) -> str:
    """Escape a string for safe embedding in an AGE Cypher single-quoted literal.

    AGE's cypher() cannot bind parameters, so values are interpolated into the query
    text. Backslash is escaped first (so the escape char itself can't combine with the
    quote escape to break out), then the single quote; control characters are rejected.
    """
    if any(ord(ch) < 0x20 for ch in value):
        raise ValueError("graph string values may not contain control characters")
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _validate_rel_type(kind: str) -> str:
    """Validate an (unquotable) Cypher relationship type as a bare identifier."""
    if not _REL_TYPE_RE.match(kind):
        raise ValueError(f"invalid relationship type: {kind!r}")
    return kind


def _prepare(session: Session) -> None:
    # AGE functions live in ag_catalog; make them resolvable for this session.
    session.execute(text('SET search_path = ag_catalog, "$user", public'))


def relate(session: Session, src: str, dst: str, kind: str = "KNOWS") -> None:
    """Create two Person nodes (by name) and a typed relationship between them.

    ``src``/``dst``/``kind`` are interpolated into the Cypher text — AGE's cypher()
    cannot bind them as parameters — so they are escaped/validated here first
    (``_escape_literal`` / ``_validate_rel_type``) to keep interpolation injection-safe.
    """
    _prepare(session)
    # SQLAlchemy's text() treats :name as a bind parameter; escape the relationship-type
    # colon with \: so it passes through as a literal colon in the Cypher clause.
    session.execute(
        text(
            f"SELECT * FROM cypher('{_GRAPH}', $$ "
            f"MERGE (a:Person {{name: '{_escape_literal(src)}'}}) "
            f"MERGE (b:Person {{name: '{_escape_literal(dst)}'}}) "
            f"MERGE (a)-[\\:{_validate_rel_type(kind)}]->(b) $$) AS (v agtype)"
        )
    )
    session.commit()


def neighbors(session: Session, name: str) -> list[str]:
    """Names directly reachable from `name` by any outgoing relationship.

    ``name`` is interpolated into the Cypher text — AGE's cypher() cannot bind it
    as a parameter — so it is escaped (``_escape_literal``) before interpolation.
    """
    _prepare(session)
    rows = session.execute(
        text(
            f"SELECT * FROM cypher('{_GRAPH}', $$ "
            f"MATCH (a:Person {{name: '{_escape_literal(name)}'}})-->(b:Person) RETURN b.name $$) AS (name agtype)"
        )
    )
    # agtype string results come back JSON-quoted (e.g. '"beta"'); strip the quotes.
    return [str(row.name).strip('"') for row in rows]
