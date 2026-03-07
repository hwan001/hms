# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```sh
# 의존성 설치
uv sync

# FastAPI 백엔드 실행 (port 8000)
uv run main.py

# NiceGUI UI 실행
uv run python app_ui.py

# 전체 테스트
uv run python -m pytest

# 특정 테스트 파일만 실행
uv run python -m pytest tests/spending/test_service.py

# 특정 테스트 함수만 실행
uv run python -m pytest tests/spending/test_router.py::test_function_name -v
```

API 문서는 `APP_ENV=development`(기본값) 일 때만 `http://127.0.0.1:8000/docs`에서 확인 가능.

## Architecture

두 개의 독립적인 진입점이 공유 도메인 레이어를 사용하는 구조:

- **`main.py`** — FastAPI 백엔드 (REST API, uvicorn)
- **`app_ui.py`** — NiceGUI 프론트엔드 (async 페이지 라우팅)

### 도메인 구조

각 도메인(`spending`, `inventory`, `cooking`, `finance`)은 동일한 레이어 구조를 가진다:

```
domains/<domain>/
  models.py    — SQLAlchemy ORM 모델 (Base 상속)
  schemas.py   — Pydantic 스키마 (Create/Update/Read)
  service.py   — 비즈니스 로직 (static async 메서드)
  router.py    — FastAPI 라우터 (spending/inventory/cooking만 존재)
```

`finance` 도메인은 FastAPI 라우터 없이 UI에서 직접 서비스를 호출한다.

### HMSEngine (핵심 추상화)

`core/engine.py`의 `HMSEngine`은 모든 쓰기 작업의 단일 진입점이다.

```python
from core.engine import engine

await engine.execute("domain", "action", db, **kwargs)
```

- 각 도메인 핸들러(`core/handlers/<domain>.py`)가 `match action:` 구문으로 서비스 메서드를 디스패치
- `engine.execute()` 내부에서 자동으로 `db.commit()` / 예외 시 `db.rollback()` 처리
- `execute_blueprint()` — 여러 도메인에 걸친 원자적 복합 작업 (재고 입출고 등)
- UI에서는 `engine.execute()`를 직접 호출하고, FastAPI 라우터에서도 동일하게 사용

### DB 세션 패턴

- FastAPI 라우터: `get_db()` (generator, `Depends` 주입)
- UI/서비스 직접 호출: `db_session()` (contextmanager, `with db_session() as db:`)
- `database.py`의 `init_db()`는 앱 시작 시 모든 모델을 import해 테이블을 생성하며, 기존 DB 마이그레이션(컬럼 추가, 스키마 변경)도 여기서 처리

### UI 레이어 (`app_ui.py` + `ui/`)

- NiceGUI 기반 SPA, 각 페이지는 `async def render_<page>()` 함수
- 동적 UI 갱신: `container.clear()` + `with container:` 로 재빌드 (컴포넌트 상태 유지 불가)
- 다이얼로그 내 상태는 mutable dict (`state = {"id": None}`)로 클로저에서 공유
- 차트: `ui.echart()` 사용

### 새 도메인 추가 시 체크리스트

1. `domains/<domain>/` 아래 models/schemas/service 생성
2. `core/handlers/<domain>.py` 핸들러 작성 (`match action:` 패턴)
3. `core/engine.py`에 `self.register("<domain>", <Handler>())` 추가
4. `database.py`의 `init_db()`에 `import domains.<domain>.models` 추가
5. `core/engine.py`의 `clear_all()`에도 동일하게 import 추가
6. `app_ui.py`에 라우트 및 `ui/pages/<domain>.py` 추가
7. `ui/layout.py`에 네비게이션 버튼 추가

### 테스트 구조

`tests/conftest.py`의 `db` fixture는 인메모리 SQLite를 사용.
테스트에 새 도메인 모델이 필요하면 conftest에 해당 models import를 추가해야 한다.
