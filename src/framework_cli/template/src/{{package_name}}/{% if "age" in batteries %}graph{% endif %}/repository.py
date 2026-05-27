from sqlalchemy import text
from sqlalchemy.orm import Session

_GRAPH = "app_graph"


def _prepare(session: Session) -> None:
    # AGE functions live in ag_catalog; make them resolvable for this session.
    session.execute(text('SET search_path = ag_catalog, "$user", public'))


def relate(session: Session, src: str, dst: str, kind: str = "KNOWS") -> None:
    """Create two Person nodes (by name) and a typed relationship between them.

    ``src``/``dst``/``kind`` are interpolated into the Cypher text — AGE's cypher()
    cannot bind them as parameters — so pass only trusted, app-controlled values.
    """
    _prepare(session)
    # SQLAlchemy's text() treats :name as a bind parameter; escape the relationship-type
    # colon with \: so it passes through as a literal colon in the Cypher clause.
    session.execute(
        text(
            f"SELECT * FROM cypher('{_GRAPH}', $$ "
            f"MERGE (a:Person {{name: '{src}'}}) MERGE (b:Person {{name: '{dst}'}}) "
            f"MERGE (a)-[\\:{kind}]->(b) $$) AS (v agtype)"
        )
    )
    session.commit()


def neighbors(session: Session, name: str) -> list[str]:
    """Names directly reachable from `name` by any outgoing relationship.

    ``name`` is interpolated into the Cypher text — AGE's cypher() cannot bind
    it as a parameter — so pass only trusted, app-controlled values.
    """
    _prepare(session)
    rows = session.execute(
        text(
            f"SELECT * FROM cypher('{_GRAPH}', $$ "
            f"MATCH (a:Person {{name: '{name}'}})-->(b:Person) RETURN b.name $$) AS (name agtype)"
        )
    )
    # agtype string results come back JSON-quoted (e.g. '"beta"'); strip the quotes.
    return [str(row.name).strip('"') for row in rows]
