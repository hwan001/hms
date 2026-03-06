import pandas as pd
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from .models import Recipe, RecipeIngredient, RecipeStep
from .schemas import RecipeCreate, RecipeUpdate
from domains.inventory.models import Inventory, InventoryHistory


class RecipeService:

    @staticmethod
    async def create_recipe(db: Session, recipe_data: RecipeCreate) -> Recipe:
        """요리 완료: 레시피 저장 + 재료 차감 + 단계 저장 + 결과물 재고 등록"""
        recipe = Recipe(
            name=recipe_data.name,
            servings=recipe_data.servings,
            note=recipe_data.note,
            output_name=recipe_data.output_name,
            output_amount=recipe_data.output_amount,
            output_unit=recipe_data.output_unit,
            output_to_inventory=recipe_data.output_to_inventory,
        )
        db.add(recipe)
        db.flush()

        # 재료 저장 + 재고 차감
        for ing in recipe_data.ingredients:
            db.add(RecipeIngredient(
                recipe_id=recipe.id,
                item_id=ing.item_id,
                item_name=ing.item_name,
                amount_used=ing.amount_used,
                unit=ing.unit,
            ))
            if ing.item_id:
                item = db.query(Inventory).filter(Inventory.id == ing.item_id).first()
                if item and item.current_weight is not None:
                    new_weight = max(0.0, item.current_weight - ing.amount_used)
                    old_weight = item.current_weight
                    item.current_weight = new_weight
                    db.add(InventoryHistory(
                        item_id=ing.item_id,
                        event_type="사용",
                        item_name=item.name,
                        measured_weight=new_weight,
                        usage_amount=old_weight - new_weight,
                        note=f"요리: {recipe_data.name}",
                    ))

        # 단계 저장
        for step in recipe_data.steps:
            db.add(RecipeStep(
                recipe_id=recipe.id,
                step_no=step.step_no,
                title=step.title,
                description=step.description,
                ingredients_note=step.ingredients_note,
            ))

        # 결과물 재고 등록
        if recipe_data.output_to_inventory and recipe_data.output_name:
            from datetime import datetime as _dt
            now = _dt.now()
            prefix = f"INV-{now.strftime('%Y%m%d')}-"
            last = db.query(Inventory.item_no).filter(
                Inventory.item_no.like('INV-%')
            ).order_by(Inventory.item_no.desc()).first()
            seq = 1
            if last and last[0]:
                try:
                    seq = int(last[0].split('-')[-1]) + 1
                except (IndexError, ValueError):
                    seq = 1

            output_item = Inventory(
                domain="요리",
                category="소모품",
                name=recipe_data.output_name,
                quantity=1,
                start_weight=recipe_data.output_amount if recipe_data.output_unit == 'g' else None,
                memo=f"요리 결과물: {recipe_data.name}",
            )
            output_item.item_no = f"{prefix}{seq:08d}"
            if output_item.start_weight is not None:
                output_item.current_weight = output_item.start_weight
            db.add(output_item)
            db.flush()
            db.add(InventoryHistory(
                item_id=output_item.id,
                event_type="등록",
                item_name=output_item.name,
                measured_weight=output_item.start_weight,
                usage_amount=0.0,
                note=f"요리 결과물 자동 등록 ({recipe_data.name})",
            ))

        db.flush()
        db.refresh(recipe)
        return recipe

    @staticmethod
    async def get_recipes(db: Session, search: str = None, limit: int = 50) -> list:
        """레시피 목록 조회 (재료·단계도 함께 로드)"""
        query = db.query(Recipe).options(
            joinedload(Recipe.ingredients).joinedload(RecipeIngredient.item),
            joinedload(Recipe.steps),
        )
        if search:
            query = query.filter(Recipe.name.ilike(f"%{search}%"))
        return query.order_by(desc(Recipe.created_at)).limit(limit).all()

    @staticmethod
    async def update_recipe(db: Session, recipe_id: str, update_data: RecipeUpdate) -> Recipe | None:
        """레시피 별점·메모·이름 수정"""
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if not recipe:
            return None
        data = update_data.model_dump(exclude_none=True)
        # rating=0 같이 falsy지만 유효한 값 처리
        if 'rating' in update_data.model_dump() and update_data.rating is not None:
            recipe.rating = update_data.rating
        for field, val in data.items():
            setattr(recipe, field, val)
        db.flush()
        db.refresh(recipe)
        return recipe

    @staticmethod
    async def delete_recipe(db: Session, recipe_id: str) -> bool:
        """레시피 삭제"""
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if not recipe:
            return False
        db.delete(recipe)
        db.flush()
        return True

    @staticmethod
    def export_to_csv_bytes(db: Session) -> bytes:
        """레시피 전체를 flat CSV bytes로 반환 (재료·단계는 세미콜론 구분)"""
        import io
        import pandas as pd
        from sqlalchemy import desc

        recipes = db.query(Recipe).options(
            __import__('sqlalchemy.orm', fromlist=['joinedload']).joinedload(Recipe.ingredients),
            __import__('sqlalchemy.orm', fromlist=['joinedload']).joinedload(Recipe.steps),
        ).order_by(desc(Recipe.created_at)).all()

        data = []
        for r in recipes:
            # 재료: "품목명|사용량|단위" 형식, 세미콜론 구분
            ing_str = ";".join(
                f"{i.item_name}|{i.amount_used}|{i.unit or 'g'}"
                for i in r.ingredients
            )
            # 단계: "제목|설명" 형식, 세미콜론 구분
            step_str = ";".join(
                f"{s.title or ''}|{s.description or ''}"
                for s in sorted(r.steps, key=lambda x: x.step_no)
            )
            data.append({
                '레시피ID':  r.id,
                '요리명':    r.name,
                '인분':      r.servings or '',
                '별점':      r.rating or '',
                '메모':      r.note or '',
                '재료':      ing_str,
                '단계':      step_str,
                '결과물명':  r.output_name or '',
                '결과물수량': r.output_amount or '',
                '결과물단위': r.output_unit or '',
                '등록일':    r.created_at.strftime('%Y-%m-%d') if r.created_at else '',
            })

        df = pd.DataFrame(data)
        buf = io.StringIO()
        df.to_csv(buf, index=False, encoding='utf-8-sig')
        return buf.getvalue().encode('utf-8-sig')

    @staticmethod
    def import_csv_from_bytes(content: bytes, db: Session) -> dict:
        """CSV bytes로 레시피 일괄 등록"""
        from core.utils import decode_csv_bytes
        from .schemas import RecipeCreate, RecipeIngredientCreate, RecipeStepCreate
        
        try:
            df = decode_csv_bytes(content)
            
            # 매핑 가능한 컬럼들 ('요리명', '인분', '별점', '메모', '재료', '단계', '결과물명', '결과물수량', '결과물단위')
            if '요리명' not in df.columns:
                raise ValueError("필수 컬럼 '요리명' 누락")
                
            new_count = 0
            for _, row in df.iterrows():
                name = str(row.get('요리명', '')).strip()
                if not name or name == 'nan':
                    continue
                    
                servings = int(row['인분']) if pd.notna(row.get('인분')) else None
                rating = float(row['별점']) if pd.notna(row.get('별점')) else None
                note = str(row.get('메모', '')).strip() if pd.notna(row.get('메모')) else None
                
                output_name = str(row.get('결과물명', '')).strip() if pd.notna(row.get('결과물명')) else None
                output_amount = float(row['결과물수량']) if pd.notna(row.get('결과물수량')) else None
                output_unit = str(row.get('결과물단위', '')).strip() if pd.notna(row.get('결과물단위')) else None
                
                # 재료 파싱 (품목명|사용량|단위;...)
                ingredients = []
                ing_raw = str(row.get('재료', ''))
                if ing_raw and ing_raw != 'nan':
                    for part in ing_raw.split(';'):
                        if not part.strip(): continue
                        tokens = part.split('|')
                        item_name = tokens[0].strip() if len(tokens) > 0 else "알 수 없음"
                        amt = float(tokens[1]) if len(tokens) > 1 and tokens[1].strip() else 0.0
                        unit = tokens[2].strip() if len(tokens) > 2 else 'g'
                        ingredients.append(RecipeIngredientCreate(
                            item_name=item_name, amount_used=amt, unit=unit
                        ))
                
                # 단계 파싱 (제목|설명;...)
                steps = []
                step_raw = str(row.get('단계', ''))
                if step_raw and step_raw != 'nan':
                    for idx, part in enumerate(step_raw.split(';')):
                        if not part.strip(): continue
                        tokens = part.split('|')
                        title = tokens[0].strip() if len(tokens) > 0 and tokens[0].strip() else None
                        desc = tokens[1].strip() if len(tokens) > 1 and tokens[1].strip() else ""
                        steps.append(RecipeStepCreate(
                            step_no=idx+1, title=title, description=desc
                        ))
                
                recipe_data = RecipeCreate(
                    name=name,
                    servings=servings,
                    rating=rating,
                    note=note,
                    ingredients=ingredients,
                    steps=steps,
                    output_name=output_name,
                    output_amount=output_amount,
                    output_unit=output_unit,
                    output_to_inventory=True if output_name else False
                )
                
                # 중첩 로직 호출을 위해 이미 구현된 create_recipe는 async이므로 동기 컨텍스트에서 우회 처리
                # (빠른 일괄 처리를 위해 직렬화된 ORM 모델을 직접 생성)
                r = Recipe(
                    name=recipe_data.name,
                    servings=recipe_data.servings,
                    rating=recipe_data.rating,
                    note=recipe_data.note,
                    output_name=recipe_data.output_name,
                    output_amount=recipe_data.output_amount,
                    output_unit=recipe_data.output_unit,
                    output_to_inventory=recipe_data.output_to_inventory,
                )
                db.add(r)
                db.flush()
                
                for ing in recipe_data.ingredients:
                    db.add(RecipeIngredient(
                        recipe_id=r.id,
                        item_name=ing.item_name,
                        amount_used=ing.amount_used,
                        unit=ing.unit
                    ))
                for st in recipe_data.steps:
                    db.add(RecipeStep(
                        recipe_id=r.id,
                        step_no=st.step_no,
                        title=st.title,
                        description=st.description,
                        ingredients_note=st.ingredients_note
                    ))
                new_count += 1
                
            db.flush()  # 개별 서비스에서는 flush만 수행, commit은 Engine에서 처리합니다.
            return {"status": "success", "message": f"레시피 CSV 등록 완료! (신규: {new_count}건)"}
        except Exception as e:
            raise RuntimeError(f"CSV 처리 오류: {str(e)}")

    @staticmethod
    def restore_from_csv_bytes(content: bytes, db: Session) -> dict:
        """
        [Restore] 레시피 전체 복원.
        기존 레시피(재료·단계 cascade 삭제) 전체 삭제 후 원래 ID로 재삽입.
        레시피ID 컬럼이 없으면 일반 import 로 폴백.
        """
        import pandas as pd
        from core.utils import decode_csv_bytes
        from .schemas import RecipeIngredientCreate, RecipeStepCreate

        try:
            df = decode_csv_bytes(content)
            if '요리명' not in df.columns:
                raise ValueError("필수 컬럼 '요리명' 누락")

            import uuid as _uuid
            recipe_rows, ing_rows, step_rows = [], [], []
            for _, row in df.iterrows():
                name = str(row.get('요리명', '')).strip()
                if not name or name == 'nan':
                    continue

                recipe_id = str(row['레시피ID']).strip() if pd.notna(row.get('레시피ID')) else str(_uuid.uuid4())
                recipe_rows.append({
                    'id': recipe_id,
                    'name': name,
                    'servings': int(row['인분']) if pd.notna(row.get('인분')) else None,
                    'rating': float(row['별점']) if pd.notna(row.get('별점')) else None,
                    'note': str(row.get('메모', '')).strip() if pd.notna(row.get('메모')) else None,
                    'output_name': str(row.get('결과물명', '')).strip() if pd.notna(row.get('결과물명')) else None,
                    'output_amount': float(row['결과물수량']) if pd.notna(row.get('결과물수량')) else None,
                    'output_unit': str(row.get('결과물단위', '')).strip() if pd.notna(row.get('결과물단위')) else None,
                    'output_to_inventory': False,
                })

                ing_raw = str(row.get('재료', ''))
                if ing_raw and ing_raw != 'nan':
                    for part in ing_raw.split(';'):
                        if not part.strip():
                            continue
                        tokens = part.split('|')
                        ing_rows.append({
                            'id': str(_uuid.uuid4()),
                            'recipe_id': recipe_id,
                            'item_name': tokens[0].strip() if tokens else '알 수 없음',
                            'amount_used': float(tokens[1]) if len(tokens) > 1 and tokens[1].strip() else 0.0,
                            'unit': tokens[2].strip() if len(tokens) > 2 else 'g',
                        })

                step_raw = str(row.get('단계', ''))
                if step_raw and step_raw != 'nan':
                    for idx, part in enumerate(step_raw.split(';')):
                        if not part.strip():
                            continue
                        tokens = part.split('|')
                        step_rows.append({
                            'id': str(_uuid.uuid4()),
                            'recipe_id': recipe_id,
                            'step_no': idx + 1,
                            'title': tokens[0].strip() if tokens and tokens[0].strip() else None,
                            'description': tokens[1].strip() if len(tokens) > 1 and tokens[1].strip() else '',
                            'ingredients_note': None,
                        })

            from database import engine as sqla_engine
            with sqla_engine.begin() as conn:
                RecipeIngredient.__table__.drop(conn, checkfirst=True)
                RecipeStep.__table__.drop(conn, checkfirst=True)
                Recipe.__table__.drop(conn, checkfirst=True)
                Recipe.__table__.create(conn, checkfirst=True)
                RecipeStep.__table__.create(conn, checkfirst=True)
                RecipeIngredient.__table__.create(conn, checkfirst=True)
                if recipe_rows:
                    conn.execute(Recipe.__table__.insert(), recipe_rows)
                if step_rows:
                    conn.execute(RecipeStep.__table__.insert(), step_rows)
                if ing_rows:
                    conn.execute(RecipeIngredient.__table__.insert(), ing_rows)
            return {"status": "success", "message": f"레시피 복원 완료! ({len(recipe_rows)}건)"}
        except Exception as e:
            raise RuntimeError(f"CSV 처리 오류: {str(e)}")
