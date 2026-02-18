
프로젝트 셋팅
```sh
uv init
uv add fastapi uvicorn pandas sqlalchemy python-multipart
uv add --dev pytest httpx # 개발용
uv add nicegui # ui
```

실행
```sh
uv sync
uv run main.py # be
uv run python app_ui.py # ui
```

### Tests
csv 파일 업로드
```sh
curl -X POST "http://localhost:8000/api/v1/spending/upload-csv" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@spending.csv"
```

pytest
```sh
uv run pytest --version
# uv run pytest
uv run python -m pytest
```

### Docs
- http://127.0.0.1:8000/docs#/ (개발모드일 때만 작동)
     - 개발모드는 환경변수 기준으로 판단 `APP_ENV=development`