from enum import Enum
from pydantic import BaseModel


class OrderStatus(Enum):
    NEW = "new"
    PAID = "paid"
    SHIPPED = "shipped"


class Order(BaseModel):
    id: int
    status: OrderStatus
