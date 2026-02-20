from fastapi import APIRouter, UploadFile, File, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
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
    
    return await SpendingService.process_csv_upload(file, db)

@router.get("/stats", summary="지출 내역 통계 조회")
async def get_spending_stats(db: Session = Depends(get_db)):
    return await SpendingService.get_stats(db)

@router.patch("/{record_id}", summary="지출 내역 수정")
async def update_spending(record_id: int, data: SpendingUpdate, db: Session = Depends(get_db)):
    # Pydantic 모델의 한글 필드명을 영문 DB 필드명으로 매핑하여 전달
    # schemas.py의 SpendingUpdate 구조에 맞춰 수동 매핑하거나 자동화 로직 필요
    mapping = {"구분": "category", "메모": "memo", "출금": "outcome", "입금": "income", "일시": "date"}
    update_dict = {mapping[k]: v for k, v in data.model_dump().items() if v is not None and k in mapping}
    
    return await SpendingService.update_spending(db, record_id, update_dict)

@router.delete("/{record_id}", summary="지출 내역 삭제")
async def delete_spending(record_id: int, db: Session = Depends(get_db)):
    return await SpendingService.delete_spending(db, record_id)