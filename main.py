import os
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from domains.spending.router import router as spending_router
from database import init_db_from_schema
from common.config import CORS_ORIGINS

ENV = os.getenv("APP_ENV", "development")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db_from_schema()
    yield

# 개발 환경일 때만 docs_url, redoc_url 활성화
if ENV == "development":
    app = FastAPI(
        lifespan=lifespan,
        title="Spending Tracker API",
        description="가계부 관리를 위한 백엔드 API",
        version="1.0.0"
    )
else:
    # 운영 환경에서는 문서를 숨김
    app = FastAPI(
        lifespan=lifespan,
        docs_url=None, 
        redoc_url=None,
        openapi_url=None
    )

# middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# router
app.include_router(spending_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)