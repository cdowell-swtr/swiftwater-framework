from sqlalchemy.orm import DeclarativeBase


class ControlBase(DeclarativeBase):
    """Declarative base for control-plane (identity/authz/tenant-registry) models."""
