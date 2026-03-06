import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_get_spending_pagination():
    # 주소에 /api/v1 추가
    response = client.get("/api/v1/spending/?page=1&size=5")
    
    assert response.status_code == 200
    res_data = response.json()
    
    assert "pagination" in res_data
    assert res_data["pagination"]["page"] == 1
    assert res_data["pagination"]["size"] == 5
    assert len(res_data["data"]) <= 5 

def test_invalid_pagination_params():
    # 주소에 /api/v1 추가
    # ge=1 설정 때문에 422 에러가 나야 함 (단, size=0 허용 로직 확인 필요)
    response = client.get("/api/v1/spending/?page=0")
    
    assert response.status_code == 422

def test_get_stats_structure():
    # 주소에 /api/v1 추가
    response = client.get("/api/v1/spending/stats")
    assert response.status_code == 200
    data = response.json()
    assert "monthly_trend" in data
    assert "category_distribution" in data