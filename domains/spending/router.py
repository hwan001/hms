from fastapi import APIRouter, UploadFile, File, Query
from typing import Optional
from .service import SpendingService
from .schemas import SpendingResponse, UploadResponse, SpendingUpdate
from database import engine, TABLE_NAME

router = APIRouter(prefix="/spending", tags=["Spending"])

@router.get("/", response_model=SpendingResponse, summary="지출 내역 목록 조회")
async def get_spending(
    category: Optional[str] = Query(None, description="구분 키워드 필터"),
    start_date: Optional[str] = Query(None, description="시작 날짜 (YYYY.MM.DD)"),
    end_date: Optional[str] = Query(None, description="종료 날짜 (YYYY.MM.DD)"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    size: int = Query(20, ge=0, le=1000, description="페이지당 데이터 개수 (0이면 전체 조회)")
):
    """
    지출 내역을 필터링하여 페이징 형태로 가져옵니다.
    - **category**: '식비', '교통' 등 키워드
    - **page**: 시작 페이지 (1부터)
    - **size**: 페이지당 데이터 개수 (0이면 전체 조회)
    """
    return await SpendingService.get_spending_list(
        engine, TABLE_NAME, category, start_date, end_date, page, size
    )

@router.post("/upload-csv", response_model=UploadResponse, summary="CSV 파일 업로드")
async def upload_csv(file: UploadFile = File(...)):
    """
    포맷에 맞는 csv 파일을 업로드하여 지출 내역을 추가합니다.
    """
    if not file.filename.endswith('.csv'):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="CSV 파일만 업로드 가능합니다.")
    
    return await SpendingService.process_csv_upload(file, engine, TABLE_NAME)

@router.get("/stats", summary="지출 내역 통계 조회")
async def get_spending_stats():
    return await SpendingService.get_stats(engine, TABLE_NAME)

@router.patch("/{record_id}", summary="지출 내역 수정")
async def update_spending(record_id: int, data: SpendingUpdate):
    update_dict = {k: v for k, v in data.model_dump().items() if v is not None}
    return await SpendingService.update_spending(engine, TABLE_NAME, record_id, update_dict)

@router.delete("/{record_id}", summary="지출 내역 삭제")
async def delete_spending(record_id: int):
    return await SpendingService.delete_spending(engine, TABLE_NAME, record_id)