from fastapi import APIRouter, UploadFile, File, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
from core.engine import engine
from .service import SpendingService
from .schemas import SpendingResponse, UploadResponse, SpendingUpdate

router = APIRouter(prefix="/spending", tags=["Spending"])

@router.get("/", response_model=SpendingResponse, summary="지출 내역 목록 조회")
async def get_spending(
    category: Optional[str] = Query(None, description="구분 키워드 필터"),
    start_date: Optional[str] = Query(None, description="시작 날짜 (YYYY.MM.DD)"),
    end_date: Optional[str] = Query(None, description="종료 날짜 (YYYY.MM.DD)"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(20, ge=0, le=1000, description="페이지당 데이터 개수 (0이면 전체 조회)"),
    db: Session = Depends(get_db)
):
    return await SpendingService.get_spending_list(
        db, category, start_date, end_date, page, size
    )

@router.post("/upload-csv", response_model=UploadResponse, summary="CSV 파일 업로드")
async def upload_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="CSV 파일만 업로드 가능합니다.")

    content = await file.read()
    return await engine.execute("spending", "import_csv", db, content=content)

@router.get("/stats", summary="지출 내역 통계 조회")
async def get_spending_stats(db: Session = Depends(get_db)):
    return await SpendingService.get_stats(db)

@router.patch("/{record_id}", summary="지출 내역 수정")
async def update_spending(record_id: int, data: SpendingUpdate, db: Session = Depends(get_db)):
    update_dict = data.model_dump(exclude_none=True)
    return await engine.execute("spending", "update_spending", db, record_id=record_id, update_data=update_dict)

@router.delete("/{record_id}", summary="지출 내역 삭제")
async def delete_spending(record_id: int, db: Session = Depends(get_db)):
    return await engine.execute("spending", "delete_spending", db, record_id=record_id)