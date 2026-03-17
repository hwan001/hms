import asyncio
import io
import uuid as _uuid_mod
from calendar import monthrange
from datetime import date, timedelta
from typing import Optional, List
from uuid import uuid4

import pandas as pd
from sqlalchemy.orm import Session, joinedload

from domains.finance.models import Portfolio, PortfolioHolding, SimulationSession
from domains.finance.schemas import (
    PortfolioCreate, PortfolioUpdate,
    HoldingCreate, HoldingUpdate,
    SimulationCreate,
)


class FinanceService:

    # ── Portfolio CRUD ──────────────────────────────────────

    @staticmethod
    async def get_portfolios(db: Session) -> List[Portfolio]:
        return db.query(Portfolio).order_by(Portfolio.created_at).all()

    @staticmethod
    async def get_portfolio(db: Session, portfolio_id: str) -> Optional[Portfolio]:
        return (
            db.query(Portfolio)
            .options(joinedload(Portfolio.holdings))
            .filter(Portfolio.id == portfolio_id)
            .first()
        )

    @staticmethod
    async def create_portfolio(db: Session, data: PortfolioCreate) -> Portfolio:
        p = Portfolio(id=str(uuid4()), **data.model_dump())
        db.add(p)
        return p

    @staticmethod
    async def update_portfolio(db: Session, portfolio_id: str, data: PortfolioUpdate) -> Portfolio:
        p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not p:
            raise ValueError(f"Portfolio {portfolio_id} not found")
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(p, k, v)
        return p

    @staticmethod
    async def delete_portfolio(db: Session, portfolio_id: str) -> None:
        p = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if p:
            db.delete(p)

    # ── Holdings CRUD ───────────────────────────────────────

    @staticmethod
    async def add_holding(db: Session, data: HoldingCreate) -> PortfolioHolding:
        h = PortfolioHolding(id=str(uuid4()), **data.model_dump())
        db.add(h)
        return h

    @staticmethod
    async def update_holding(db: Session, holding_id: str, data: HoldingUpdate) -> PortfolioHolding:
        h = db.query(PortfolioHolding).filter(PortfolioHolding.id == holding_id).first()
        if not h:
            raise ValueError(f"Holding {holding_id} not found")
        for k, v in data.model_dump(exclude_none=True).items():
            setattr(h, k, v)
        return h

    @staticmethod
    async def delete_holding(db: Session, holding_id: str) -> None:
        h = db.query(PortfolioHolding).filter(PortfolioHolding.id == holding_id).first()
        if h:
            db.delete(h)

    # ── Stock Price (yfinance) ──────────────────────────────

    @staticmethod
    async def fetch_current_price(ticker: str) -> Optional[float]:
        def _fetch():
            try:
                import yfinance as yf
                hist = yf.Ticker(ticker).history(period="2d")
                if hist.empty:
                    return None
                return float(hist["Close"].iloc[-1])
            except Exception:
                return None
        return await asyncio.to_thread(_fetch)

    @staticmethod
    async def _fetch_price_history(ticker: str, start: date, end: date) -> dict:
        """start~end 기간 종가 히스토리 → {date_str: price}"""
        def _fetch():
            try:
                import yfinance as yf
                hist = yf.Ticker(ticker).history(
                    start=str(start), end=str(end + timedelta(days=1))
                )
                if hist.empty:
                    return {}
                return {
                    str(idx.date()): float(hist.loc[idx, "Close"])
                    for idx in hist.index
                }
            except Exception:
                return {}
        return await asyncio.to_thread(_fetch)

    @staticmethod
    def _lookup_price(price_history: dict, target: date) -> Optional[float]:
        """target 날짜 종가 조회, 없으면 이후 최대 10 영업일 탐색"""
        for i in range(10):
            d = str(target + timedelta(days=i))
            if d in price_history:
                return price_history[d]
        return None

    @staticmethod
    def _generate_buy_dates(start: date, buy_day: int) -> List[date]:
        """start 부터 오늘까지 매월 buy_day 날짜 목록"""
        today = date.today()
        dates: List[date] = []
        year, month = start.year, start.month
        while True:
            max_day = monthrange(year, month)[1]
            bd = date(year, month, min(buy_day, max_day))
            if start <= bd <= today:
                dates.append(bd)
            # 다음 달
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
            if date(year, month, 1) > today:
                break
        return dates

    # ── Simulation CRUD ─────────────────────────────────────

    @staticmethod
    async def get_simulations(db: Session) -> List[SimulationSession]:
        return (
            db.query(SimulationSession)
            .options(joinedload(SimulationSession.portfolio))
            .order_by(SimulationSession.created_at.desc())
            .all()
        )

    @staticmethod
    async def create_simulation(db: Session, data: SimulationCreate) -> SimulationSession:
        s = SimulationSession(id=str(uuid4()), **data.model_dump())
        db.add(s)
        return s

    @staticmethod
    async def delete_simulation(db: Session, session_id: str) -> None:
        s = db.query(SimulationSession).filter(SimulationSession.id == session_id).first()
        if s:
            db.delete(s)

    # ── CSV Export ──────────────────────────────────────────

    @staticmethod
    def export_portfolios_to_csv_bytes(db: Session) -> bytes:
        rows = db.query(Portfolio).order_by(Portfolio.created_at).all()
        data = [{'포트폴리오ID': p.id, '이름': p.name, '설명': p.description or ''} for p in rows]
        df = pd.DataFrame(data)
        buf = io.StringIO()
        df.to_csv(buf, index=False, encoding='utf-8-sig')
        return buf.getvalue().encode('utf-8-sig')

    @staticmethod
    def export_holdings_to_csv_bytes(db: Session) -> bytes:
        rows = db.query(PortfolioHolding).all()
        data = [{
            '보유ID': h.id, '포트폴리오ID': h.portfolio_id,
            '종목코드': h.ticker, '종목명': h.name,
            '수량': h.quantity, '평균매입가': h.avg_price,
            '통화': h.currency, '목표비율': h.target_ratio or 0,
            '메모': h.memo or '',
        } for h in rows]
        df = pd.DataFrame(data)
        buf = io.StringIO()
        df.to_csv(buf, index=False, encoding='utf-8-sig')
        return buf.getvalue().encode('utf-8-sig')

    @staticmethod
    def export_simulations_to_csv_bytes(db: Session) -> bytes:
        rows = db.query(SimulationSession).order_by(SimulationSession.created_at).all()
        data = [{
            '세션ID': s.id, '포트폴리오ID': s.portfolio_id or '',
            '이름': s.name, '월매수금액': s.monthly_amount,
            '매수일': s.buy_day, '시작일': str(s.start_date),
        } for s in rows]
        df = pd.DataFrame(data)
        buf = io.StringIO()
        df.to_csv(buf, index=False, encoding='utf-8-sig')
        return buf.getvalue().encode('utf-8-sig')

    # ── CSV Restore ─────────────────────────────────────────

    @staticmethod
    def restore_portfolios_from_csv_bytes(content: bytes, db: Session) -> dict:
        """포트폴리오 전체 복원 — 3개 테이블 모두 초기화 후 포트폴리오만 삽입."""
        from core.utils import decode_csv_bytes
        from database import engine as sqla_engine
        try:
            df = decode_csv_bytes(content)
            rows = []
            for _, row in df.iterrows():
                pid  = str(row.get('포트폴리오ID', '')).strip()
                name = str(row.get('이름', '')).strip()
                if not name or name == 'nan':
                    continue
                rows.append({
                    'id':          pid if pid and pid != 'nan' else str(_uuid_mod.uuid4()),
                    'name':        name,
                    'description': str(row['설명']).strip() if pd.notna(row.get('설명')) else None,
                })
            with sqla_engine.begin() as conn:
                PortfolioHolding.__table__.drop(conn, checkfirst=True)
                SimulationSession.__table__.drop(conn, checkfirst=True)
                Portfolio.__table__.drop(conn, checkfirst=True)
                Portfolio.__table__.create(conn, checkfirst=True)
                SimulationSession.__table__.create(conn, checkfirst=True)
                PortfolioHolding.__table__.create(conn, checkfirst=True)
                if rows:
                    conn.execute(Portfolio.__table__.insert(), rows)
            return {"status": "success", "message": f"포트폴리오 복원 완료! ({len(rows)}건)"}
        except Exception as e:
            raise RuntimeError(f"CSV 처리 오류: {str(e)}")

    @staticmethod
    def restore_holdings_from_csv_bytes(content: bytes, db: Session) -> dict:
        """보유 종목 복원 — holdings 테이블만 초기화 후 삽입."""
        from core.utils import decode_csv_bytes
        from database import engine as sqla_engine
        try:
            df = decode_csv_bytes(content)
            rows = []
            for _, row in df.iterrows():
                ticker = str(row.get('종목코드', '')).strip()
                if not ticker or ticker == 'nan':
                    continue
                hid = str(row.get('보유ID', '')).strip()
                pid = str(row.get('포트폴리오ID', '')).strip()
                rows.append({
                    'id':           hid if hid and hid != 'nan' else str(_uuid_mod.uuid4()),
                    'portfolio_id': pid if pid and pid != 'nan' else None,
                    'ticker':       ticker,
                    'name':         str(row.get('종목명', ticker)).strip(),
                    'quantity':     float(row['수량'])      if pd.notna(row.get('수량'))      else 0.0,
                    'avg_price':    float(row['평균매입가']) if pd.notna(row.get('평균매입가')) else 0.0,
                    'currency':     str(row.get('통화', 'KRW')).strip() if pd.notna(row.get('통화')) else 'KRW',
                    'target_ratio': float(row['목표비율'])  if pd.notna(row.get('목표비율'))  else 0.0,
                    'memo':         str(row['메모']).strip() if pd.notna(row.get('메모')) else None,
                })
            with sqla_engine.begin() as conn:
                PortfolioHolding.__table__.drop(conn, checkfirst=True)
                PortfolioHolding.__table__.create(conn, checkfirst=True)
                if rows:
                    conn.execute(PortfolioHolding.__table__.insert(), rows)
            return {"status": "success", "message": f"보유 종목 복원 완료! ({len(rows)}건)"}
        except Exception as e:
            raise RuntimeError(f"CSV 처리 오류: {str(e)}")

    @staticmethod
    def restore_simulations_from_csv_bytes(content: bytes, db: Session) -> dict:
        """시뮬레이션 세션 복원 — simulations 테이블만 초기화 후 삽입."""
        from core.utils import decode_csv_bytes
        from database import engine as sqla_engine
        try:
            df = decode_csv_bytes(content)
            rows = []
            for _, row in df.iterrows():
                name = str(row.get('이름', '')).strip()
                if not name or name == 'nan':
                    continue
                sid = str(row.get('세션ID', '')).strip()
                pid = str(row.get('포트폴리오ID', '')).strip()
                start_raw = str(row.get('시작일', '')).strip()
                try:
                    start_date = date.fromisoformat(start_raw) if start_raw and start_raw != 'nan' else date.today()
                except ValueError:
                    start_date = date.today()
                rows.append({
                    'id':             sid if sid and sid != 'nan' else str(_uuid_mod.uuid4()),
                    'portfolio_id':   pid if pid and pid != 'nan' else None,
                    'name':           name,
                    'monthly_amount': float(row['월매수금액']) if pd.notna(row.get('월매수금액')) else 500_000.0,
                    'buy_day':        int(row['매수일'])       if pd.notna(row.get('매수일'))    else 1,
                    'start_date':     start_date,
                })
            with sqla_engine.begin() as conn:
                SimulationSession.__table__.drop(conn, checkfirst=True)
                SimulationSession.__table__.create(conn, checkfirst=True)
                if rows:
                    conn.execute(SimulationSession.__table__.insert(), rows)
            return {"status": "success", "message": f"시뮬레이션 세션 복원 완료! ({len(rows)}건)"}
        except Exception as e:
            raise RuntimeError(f"CSV 처리 오류: {str(e)}")

    # ── DCA Simulation Engine ───────────────────────────────

    @staticmethod
    async def run_simulation(db: Session, session_id: str) -> dict:
        """
        DCA 시뮬레이션 실행.
        start_date 부터 오늘까지 매월 buy_day 에 monthly_amount 를
        포트폴리오 종목 비율대로 매수한 결과를 계산한다.
        """
        session = (
            db.query(SimulationSession)
            .options(
                joinedload(SimulationSession.portfolio)
                .joinedload(Portfolio.holdings)
            )
            .filter(SimulationSession.id == session_id)
            .first()
        )
        if not session:
            return {"error": "시뮬레이션을 찾을 수 없습니다."}
        if not session.portfolio:
            return {"error": "연결된 포트폴리오가 없습니다."}

        valid_holdings = [
            h for h in session.portfolio.holdings
            if (h.target_ratio or 0) > 0
        ]
        if not valid_holdings:
            return {"error": "목표 비율이 설정된 종목이 없습니다."}

        # DB 작업 완료 후 필요한 데이터만 추출 (DB 세션 의존 제거)
        portfolio_name = session.portfolio.name
        monthly_amount = session.monthly_amount
        buy_day = session.buy_day
        start_date = session.start_date
        total_ratio = sum(h.target_ratio for h in valid_holdings)
        holdings_meta = [
            {
                "ticker": h.ticker,
                "name": h.name,
                "currency": h.currency,
                "ratio": h.target_ratio / total_ratio,  # 정규화된 비율
                "target_ratio_raw": h.target_ratio,
            }
            for h in valid_holdings
        ]

        # 매수 날짜 목록 (과거~오늘 기준; 아직 매수일이 없으면 빈 리스트)
        buy_dates = FinanceService._generate_buy_dates(start_date, buy_day)
        today = date.today()

        # 매수 이력이 없는 경우 — 다음 매수일까지 대기 중인 상태
        if not buy_dates:
            # 다음 예정 매수일 계산
            _y, _m = start_date.year, start_date.month
            _bd = date(_y, _m, min(buy_day, monthrange(_y, _m)[1]))
            if _bd < start_date or _bd <= today:
                _m2 = _m + 1 if _m < 12 else 1
                _y2 = _y + (1 if _m == 12 else 0)
                _bd = date(_y2, _m2, min(buy_day, monthrange(_y2, _m2)[1]))
            return {
                "portfolio_name": portfolio_name,
                "buy_count": 0,
                "start_date": str(start_date),
                "end_date": str(today),
                "next_buy_date": str(_bd),
                "total_invested": 0.0,
                "total_current_value": 0.0,
                "total_pnl": 0.0,
                "total_pct": 0.0,
                "per_stock": [],
                "timeline": [],
            }

        # 가격 히스토리 병렬 조회
        tickers = [h["ticker"] for h in holdings_meta]
        histories = await asyncio.gather(
            *[FinanceService._fetch_price_history(t, start_date, today) for t in tickers],
            return_exceptions=True,
        )
        price_history = {
            t: (h if isinstance(h, dict) else {})
            for t, h in zip(tickers, histories)
        }

        # DCA 누적 계산
        shares = {t: 0.0 for t in tickers}
        costs  = {t: 0.0 for t in tickers}
        total_invested = 0.0
        timeline = []

        for bd in buy_dates:
            period_invested = 0.0
            for hm in holdings_meta:
                alloc = monthly_amount * hm["ratio"]
                price = FinanceService._lookup_price(price_history[hm["ticker"]], bd)
                if price and price > 0:
                    shares[hm["ticker"]] += alloc / price
                    costs[hm["ticker"]] += alloc
                    period_invested += alloc
            total_invested += period_invested

            # 해당 날짜 포트폴리오 평가금액 (보유 주식 × 해당일 종가)
            period_value = sum(
                shares[hm["ticker"]]
                * (FinanceService._lookup_price(price_history[hm["ticker"]], bd) or 0)
                for hm in holdings_meta
            )
            timeline.append({
                "date": str(bd),
                "invested": round(total_invested, 0),
                "value": round(period_value, 0),
            })

        # 현재 주가 병렬 조회
        cur_prices_raw = await asyncio.gather(
            *[FinanceService.fetch_current_price(t) for t in tickers],
            return_exceptions=True,
        )
        current_prices = {
            t: (p if isinstance(p, float) else None)
            for t, p in zip(tickers, cur_prices_raw)
        }

        # 종목별 요약
        per_stock = []
        total_current_value = 0.0
        for hm in holdings_meta:
            t = hm["ticker"]
            total_shares = shares[t]
            total_cost = costs[t]
            cur_price = current_prices.get(t)
            cur_val = (cur_price * total_shares) if cur_price else total_cost
            total_current_value += cur_val
            per_stock.append({
                "ticker": t,
                "name": hm["name"],
                "target_ratio": hm["target_ratio_raw"],
                "currency": hm["currency"],
                "shares": total_shares,
                "avg_cost": (total_cost / total_shares) if total_shares > 0 else 0,
                "current_price": cur_price,
                "total_cost": total_cost,
                "current_value": cur_val,
                "pnl": cur_val - total_cost,
                "pnl_pct": ((cur_val - total_cost) / total_cost * 100) if total_cost > 0 else 0,
            })

        total_pnl = total_current_value - total_invested
        total_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

        return {
            "portfolio_name": portfolio_name,
            "buy_count": len(buy_dates),
            "start_date": str(start_date),
            "end_date": str(today),
            "total_invested": total_invested,
            "total_current_value": total_current_value,
            "total_pnl": total_pnl,
            "total_pct": total_pct,
            "per_stock": per_stock,
            "timeline": timeline,
        }
