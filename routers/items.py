from fastapi import APIRouter
from pydantic import BaseModel
from collections.abc import AsyncIterable, Iterable
#items = [ "Item 1", "Item 2", "Item 3", "Item 4" ]

router=APIRouter()

items=[]
class Items(BaseModel):
    idd: int
    name: str

@router.get("/create/v2", response_model=list[Items])
async def create_items_v2() -> AsyncIterable[Items]:
    for i in range(0, 5):
        new_item=Items(idd=i, name=f"item {i}")
        items.append(new_item)
    
    return items  

@router.post("/create/v1", response_model=Items)
async def create_items_v1(item: Items) -> Items:
    items.append(item)
    return item

# @router.post("/create/v0")
# async def create_item_v0(item: str):
#     items.append(item)


@router.get("")
async def get_items():
    return items


@router.get("/{id}")
async def get_item(id: int):
    return items[id]



@router.delete("/{id}")
async def delete_item(id: int):
    del items[id]