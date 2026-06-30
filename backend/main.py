# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database.db_handler import get_latest_news, init_db

app = FastAPI(title="실시간 뉴스 요약 프로젝트 API 서버")

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

if __name__ == "__main__":
    import uvicorn
    # 8000번 포트로 API 서버 가동
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)