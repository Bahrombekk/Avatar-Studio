"""Avatar CRUD endpointlari (/api/avatars)."""
from fastapi import APIRouter, Body, HTTPException

from app.services import avatar_store

router = APIRouter(prefix="/api/avatars", tags=["avatars"])


@router.get("")
def list_avatars():
    return {"avatars": avatar_store.list_avatars()}


@router.get("/{avatar_id}")
def get_avatar(avatar_id: str):
    a = avatar_store.get_avatar(avatar_id)
    if not a:
        raise HTTPException(404, "Avatar topilmadi")
    return a


@router.post("")
def create_avatar(data: dict = Body(...)):
    return avatar_store.create_avatar(data)


@router.put("/{avatar_id}")
def update_avatar(avatar_id: str, data: dict = Body(...)):
    a = avatar_store.update_avatar(avatar_id, data)
    if not a:
        raise HTTPException(404, "Avatar topilmadi")
    return a


@router.delete("/{avatar_id}")
def delete_avatar(avatar_id: str):
    if not avatar_store.delete_avatar(avatar_id):
        raise HTTPException(404, "Avatar topilmadi")
    return {"deleted": avatar_id}
