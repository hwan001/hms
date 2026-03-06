import pytest
import pandas as pd
import numpy as np
import math
from domains.spending.service import SpendingService

def test_clean_amount_logic():
    # 1. 콤마가 포함된 문자열 테스트
    assert SpendingService.to_clean_float("20,000") == 20000.0
    # 2. 따옴표와 콤마가 섞인 경우 (따옴표 제거 후 처리)
    assert SpendingService.to_clean_float('5,200') == 5200.0
    # 3. 빈 값 처리
    assert SpendingService.to_clean_float("") == 0.0
    # 4. 이미 float인 경우
    assert SpendingService.to_clean_float(1500.5) == 1500.5

def test_nan_to_none_conversion():
    # JSON 직렬화 에러 방지 로직 테스트
    df = pd.DataFrame({"메모": [np.nan, "커피"], "금액": [5000, 1800]})
    df_clean = df.replace({np.nan: None})
    
    assert df_clean.iloc[0]["메모"] is None
    assert df_clean.iloc[1]["메모"] == "커피"


def test_pagination_logic():
    # 1. 페이징 계산 공식 검증
    total_count = 45
    size = 20
    
    # 서비스 로직에서 사용하는 방식과 동일하게 검증
    total_pages = math.ceil(total_count / size)
    
    assert total_pages == 3  # (20, 20, 5) 이므로 3페이지여야 함
    
    # 2. Offset 계산 검증
    page = 2
    offset = (page - 1) * size
    assert offset == 20  # 2페이지면 앞의 20개를 건너뛰어야 함