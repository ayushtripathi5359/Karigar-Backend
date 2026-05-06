from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Single declarative base imported by every module's models."""
    pass
