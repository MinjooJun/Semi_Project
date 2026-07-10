# main.py
<<<<<<< Updated upstream
from fastapi import FastAPI
=======
# 기존의 extract_article_text가 포함된 import 문을 아래처럼 딱 하나만 남기고 바꾸세요.
from utils.scraper import get_news_by_category

# 나머지 database 관련 import는 그대로 두시면 됩니다.
from database.db_handler import (
    DB_PATH, get_connection, init_db, get_latest_news,
    get_or_create_user, check_user_exists, toggle_favorite_in_db
)
from fastapi import FastAPI, Query, HTTPException
>>>>>>> Stashed changes
from fastapi.middleware.cors import CORSMiddleware
from database.db_handler import get_latest_news, init_db

<<<<<<< Updated upstream
app = FastAPI(title="실시간 뉴스 요약 프로젝트 API 서버")
=======
import pandas as pd
import sys
import os
# 현재 파일이 있는 폴더를 파이썬이 무조건 찾도록 강제합니다.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


app = FastAPI(title="실시간 뉴스 요약 프로젝트 API 서버 (SQLite 안전 피스 버전)")
>>>>>>> Stashed changes

# 🚨 [중요] 리액트(3000번 포트 등)와 통신할 때 발생하는 CORS 에러 원천 차단
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 단계에서는 모든 도메인 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    # 서버 켜질 때 DB 체크
    init_db()


@app.get("/")
def read_root():
    return {"message": "백엔드 API 서버가 정상 작동 중입니다."}

<<<<<<< Updated upstream
@app.get("/api/news")
def fetch_news_for_react():
    """리액트가 최신 뉴스 데이터를 요청하는 엔드포인트"""
    news_data = get_latest_news(limit=20)
    return {
        "status": "success",
        "count": len(news_data),
        "data": news_data
    }

# 📍 7/4 즐겨찾기 기능 개발 시 여기에 @app.post("/api/bookmark") 추가 예정
=======
# main.py 수정본


@app.get("/api/news")
def fetch_news_for_react(
    category: str = Query(None),  # React가 ?category=경제 보낼 때 받음
    date: str = Query(None)      # React가 ?date=2026-07-09 보낼 때 받음
):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 기본 기본 쿼리문
        query = "SELECT * FROM news WHERE 1=1"
        params = []

        # 1. 카테고리 필터링 조건 추가
        if category and category.strip():
            query += " AND category = ?"
            params.append(category.strip())

        # 2. 날짜 필터링 조건 추가 (published_at 컬럼 구조에 맞춰 LIKE 매칭이나 정제 조건)
        # 만약 DB의 published_at이 "Thu, 09 Jul 2026..." 형태라면 프론트에서 주는 날짜 형식과 맞춰야 합니다.
        if date and date.strip():
            # 예: '2026-07-09' 형태로 들어오면 DB 텍스트 포맷과 매칭되게 하거나,
            # 혹은 데이터 포맷팅에 맞춰 '09 Jul 2026' 형태로 부분 매칭(LIKE)을 시도합니다.
            # 마스터님 DB가 문자열 날짜 구조이므로 아래처럼 LIKE로 안전 방어막을 칠 수 있습니다.
            # (프론트엔드에서 형식을 맞춰주면 제일 좋습니다!)
            query += " AND published_at LIKE ?"
            params.append(f"%{date.strip()}%")

        # 최신순 정렬 및 개수 제한
        query += " ORDER BY id DESC LIMIT 50"

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        conn.close()

        return {"status": "success", "data": [dict(row) for row in rows]}

    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news/top5")
def fetch_top5_hot_issues():
    from utils.cluster import cluster_and_get_top_news
    try:
        all_recent_news = get_latest_news(limit=50)
        if not all_recent_news:
            return {"status": "success", "count": 0, "data": []}
        top5_hot_news = cluster_and_get_top_news(all_recent_news, n_clusters=5)
        return {"status": "success", "count": len(top5_hot_news), "data": top5_hot_news}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news/daily")
def fetch_daily_summary():
    """daily_summary 테이블에서 스케줄러가 쌓아둔 3대이슈 JSON을 꺼내 서빙합니다."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT title, summary_json FROM daily_summary ORDER BY id DESC LIMIT 1;"
        )
        row = cursor.fetchone()
        if row:
            return {"status": "success", "data": dict(row)}
        return {"status": "success", "data": None}
    except Exception as e:
        # 에러가 발생했을 때만 예외를 던집니다.
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 여기서는 연결만 닫습니다.
        conn.close()


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
    try:
        action_result = toggle_favorite_in_db(req.user_id, req.news_id)
        return {"status": "success", "action": action_result, "message": "즐겨찾기 변경 완료"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/news/keyword/{keyword}")
def fetch_news_by_keyword(keyword: str):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM news 
            WHERE title LIKE ? OR summary_1 LIKE ? OR summary_2 LIKE ? OR summary_3 LIKE ?
            ORDER BY id DESC LIMIT 20
        """, (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'))
        rows = cursor.fetchall()
        conn.close()
        return {"status": "success", "keyword": keyword, "data": [dict(row) for row in rows]}
    except Exception as e:
        if conn:
            conn.close()
        raise HTTPException(status_code=500, detail=str(e))
>>>>>>> Stashed changes


if __name__ == "__main__":
    import uvicorn
<<<<<<< Updated upstream
    # 8000번 포트로 API 서버 가동
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
=======
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
>>>>>>> Stashed changes
