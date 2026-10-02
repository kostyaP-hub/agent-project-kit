from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class OrderRow(Base):
    __tablename__ = "orders"


class CustomerRow(Base):
    __tablename__ = "customers"
