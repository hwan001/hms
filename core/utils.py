import io
import pandas as pd

def decode_csv_bytes(content: bytes) -> pd.DataFrame:
    """
    엑셀, Mac 등에서 저장된 다양한 인코딩의 CSV bytes를 
    안전하게 디코딩하여 pandas DataFrame으로 반환합니다.
    """
    encodings = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'mac_roman']
    last_err = None
    
    for enc in encodings:
        try:
            decoded_text = content.decode(enc)
            df = pd.read_csv(io.StringIO(decoded_text), dtype=str)
            df.columns = [c.strip() for c in df.columns]
            return df
        except Exception as e:
            last_err = e
            continue
            
    raise ValueError(f"지원하는 인코딩으로 CSV를 읽을 수 없습니다. (마지막 에러: {last_err})")
