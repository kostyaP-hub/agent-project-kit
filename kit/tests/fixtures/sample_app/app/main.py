"""Sample app HTTP entrypoint."""
from fastapi import FastAPI
from app.models import Order

api = FastAPI()


@api.get("/health")
def health():
    return {"ok": True}


@api.post("/orders")
def create_order(order: Order):
    return order


def cli():
    print("run")


if __name__ == "__main__":
    cli()
