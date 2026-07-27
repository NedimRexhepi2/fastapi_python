from fastapi import APIRouter

units = [ "Item 1", "Item 2", "Item 3", "Item 4" ]

router=APIRouter()

@router.get("")
async def get_units():
    return units

@router.get("/{id}")
async def get_unit(id: int):
    return units[id]

@router.post("")
async def create_unit(item: str):
    units.append(item)

@router.delete("/{id}")
async def delete_unit(id: int):
    del units[id]