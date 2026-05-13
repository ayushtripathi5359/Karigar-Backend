from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Single declarative base imported by every service's models."""
    pass
