# main.py
import json
import sqlite3
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# [DB 비즈니스 로직 임포트]
from database.db_handler import (
    get_connection, init_db, get_latest_news, 
    get_or_create_user, check_user_exists, toggle_favorite_in_db, 
    get_daily_summary, get_daily_summary_by_date,
    get_realtime_trend_keywords,
    get_favorites_by_user, get_favorite_ids_by_user, news_exists,  # 👈 추가
)
# [AI/알고리즘 모듈 임포트]
from utils.cluster import cluster_and_get_top_news

app = FastAPI(title="실시간 뉴스 요약 프로젝트 API 서버 (멀티라벨 통합판)")

# 프론트엔드(Vite / React 기본 포트) CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://*.vercel.app",   # Vercel 배포 주소 허용
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",  # 언니가 재배포해서 주소가 바뀌어도 대응
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SEP = "|"


def _expand_categories(row_dict):
    """
    category('경제|IT/과학') 를 그대로 두되, React 편의를 위해
    categories 배열(['경제','IT/과학']) 필드를 추가로 얹어준다.
    """
    cat = row_dict.get("category") or ""
    row_dict["categories"] = [c for c in str(cat).split(SEP) if c]
    return row_dict


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/")
def read_root():
    return {"message": "백엔드 API 서버가 정상 작동 중입니다."}


# =======================================================================
# 🔥 1. 뉴스 일반 조회 & 실시간 핫이슈 TOP 5
# =======================================================================
@app.get("/api/news")
def fetch_news_for_react(
    category: str = Query(None, description="카테고리 필터 (예: 사회/세계)"),
    date: str = Query(None, description="날짜 필터 (예: 2026-07-09)")
):
    """일반 뉴스 리스트 조회 (멀티라벨 대응: category 는 LIKE 로 부분 매칭)"""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        query = "SELECT * FROM news WHERE 1=1"
        params = []

        if category and category.strip():
            # 'A|B' 로 저장돼 있으므로 정확일치(=) 대신 부분매칭(LIKE) 사용
            query += " AND category LIKE ?"
            params.append(f"%{category.strip()}%")

        if date and date.strip():
            query += " AND published_at LIKE ?"
            params.append(f"%{date.strip()}%")

        query += " ORDER BY id DESC LIMIT 50"

        cursor.execute(query, tuple(params))
        rows = [_expand_categories(dict(row)) for row in cursor.fetchall()]
        return {"status": "success", "data": rows}

    except Exception as e:
        print(f"❌ 뉴스 필터 조회 중 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.get("/api/news/top5")
def fetch_top5_hot_issues():
    """[실시간 TOP 5] 최근 기사 50개를 K-Means로 군집화하여 탑이슈 5개 추출"""
    try:
        all_recent_news = get_latest_news(limit=50)
        if not all_recent_news:
            return {"status": "success", "count": 0, "data": []}

        top5_hot_news = cluster_and_get_top_news(all_recent_news, n_clusters=5)
        top5_hot_news = [_expand_categories(dict(n)) for n in top5_hot_news]
        return {"status": "success", "count": len(top5_hot_news), "data": top5_hot_news}
    except Exception as e:
        print(f"❌ 실시간 TOP 5 추출 중 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =======================================================================
# 🌅 2. 데일리 뉴스 종합 요약 아카이브
# =======================================================================
@app.get("/api/news/daily-summary")
def fetch_daily_summary_for_react(date: str = Query(None, description="조회할 과거 날짜 (YYYY-MM-DD)")):
    try:
        if date and date.strip():
            summary_data = get_daily_summary_by_date(date.strip())
        else:
            summary_data = get_daily_summary()

        if not summary_data:
            return {"status": "success", "data": [], "message": "요청한 날짜의 데일리 요약이 없습니다."}

        summary_data_dict = dict(summary_data)
        parsed_articles = json.loads(summary_data_dict["summary_json"])

        return {
            "status": "success",
            "date": summary_data_dict.get("created_at"),
            "data": parsed_articles
        }
    except Exception as e:
        print(f"❌ 데일리 요약 API 조회 중 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =======================================================================
# 📡 3. 실시간 트렌드 키워드 및 조건 검색 엔진
# =======================================================================
@app.get("/api/news/trend")
def fetch_realtime_trends():
    """[실시간 트렌드 키워드] 최근 뉴스 제목에서 다관왕 단어 TOP 10 역추적"""
    try:
        trend_data = get_realtime_trend_keywords(limit_news=300, top_n=10)
        return {"status": "success", "count": len(trend_data), "data": trend_data}
    except Exception as e:
        print(f"❌ 트렌드 API 분석 중 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news/keyword/{keyword}")
def fetch_news_by_keyword(keyword: str):
    """검색창 단어 매칭 뉴스 최신순 20개"""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM news
            WHERE title LIKE ? OR summary_1 LIKE ? OR summary_2 LIKE ? OR summary_3 LIKE ?
            ORDER BY id DESC LIMIT 20
        """, (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'))
        rows = [_expand_categories(dict(row)) for row in cursor.fetchall()]
        return {"status": "success", "keyword": keyword, "data": rows}
    except Exception as e:
        print(f"❌ 키워드 검색 중 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# =======================================================================
# 🔐 4. 사용자 인증(닉네임 로그인) 및 즐겨찾기
# =======================================================================
class LoginRequest(BaseModel):
    username: str


class FavoriteRequest(BaseModel):
    user_id: int
    news_id: int


@app.get("/api/check-nickname")
def check_nickname(username: str = Query(...)):
    if not username or not username.strip():
        return {"status": "error", "message": "닉네임을 입력해주세요."}
    is_duplicate = check_user_exists(username.strip())
    return {"status": "duplicate" if is_duplicate else "available"}


@app.post("/api/login")
def login_or_signup(req: LoginRequest):
    if not req.username or not req.username.strip():
        return {"status": "error", "message": "닉네임을 입력해주세요."}
    user_id = get_or_create_user(req.username.strip())
    return {"status": "success", "data": {"user_id": user_id, "username": req.username.strip()}}


@app.post("/api/favorites/toggle")
def toggle_favorite(req: FavoriteRequest):
    """하트 클릭 → 있으면 삭제, 없으면 추가 (토글)"""
    try:
        # 유령 news_id가 박히는 것을 사전 차단
        if not news_exists(req.news_id):
            raise HTTPException(status_code=404, detail="존재하지 않는 뉴스입니다.")

        action_result = toggle_favorite_in_db(req.user_id, req.news_id)
        return {
            "status": "success",
            "action": action_result,             # "added" 또는 "removed"
            "is_favorite": action_result == "added",  # 👈 리액트가 하트 색만 보고 쓰기 편하게
            "news_id": req.news_id,
            "message": "즐겨찾기에 추가했습니다." if action_result == "added" else "즐겨찾기에서 해제했습니다."
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 즐겨찾기 토글 중 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/favorites")
def fetch_favorites(user_id: int = Query(..., description="조회할 사용자 ID")):
    """[내 즐겨찾기 페이지] 하트 누른 뉴스 전체 정보를 최신순으로 반환"""
    try:
        rows = get_favorites_by_user(user_id)
        return {"status": "success", "count": len(rows), "data": rows}
    except Exception as e:
        print(f"❌ 즐겨찾기 목록 조회 중 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/favorites/ids")
def fetch_favorite_ids(user_id: int = Query(..., description="조회할 사용자 ID")):
    """[하트 상태 동기화용] 즐겨찾기한 news_id 배열만 가볍게 반환"""
    try:
        ids = get_favorite_ids_by_user(user_id)
        return {"status": "success", "count": len(ids), "data": ids}
    except Exception as e:
        print(f"❌ 즐겨찾기 ID 조회 중 오류: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    

if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
