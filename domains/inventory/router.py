from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
from . import schemas, service

router = APIRouter(prefix="/api/inventory", tags=["Inventory"])

@router.post("/", response_model=schemas.InventoryRead)
async def create_inventory_item(item: schemas.InventoryCreate, db: Session = Depends(get_db)):
    return await service.InventoryService.create_item(db, item)

@router.get("/", response_model=List[schemas.InventoryRead])
async def list_inventory_items(
    domain: Optional[str] = None, 
    category: Optional[str] = None, 
    db: Session = Depends(get_db)
):
    return await service.InventoryService.get_items(db, domain, category)

@router.post("/{item_id}/history", response_model=schemas.HistoryRead)
async def create_usage_log(
    item_id: str, 
    history: schemas.HistoryCreate, 
    db: Session = Depends(get_db)
):
    result = await service.InventoryService.add_usage_history(db, item_id, history)
    if not result:
        raise HTTPException(status_code=404, detail="품목을 찾을 수 없습니다.")
    return result