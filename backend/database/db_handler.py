import sqlite3

DB_PATH = "news_database.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 뉴스 저장 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        published_at TEXT,
        summary_1 TEXT,
        summary_2 TEXT,
        summary_3 TEXT,
        original_url TEXT UNIQUE,
        category TEXT,
        cluster_id INTEGER
    );
    """)
    
    # 2. 초간단 사용자 식별 테이블 (인증 없음)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL
    );
    """)
    
    # 3. 즐겨찾기 매핑 테이블
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookmarks (
        bookmark_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        news_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(user_id),
        FOREIGN KEY(news_id) REFERENCES news(id),
        UNIQUE(user_id, news_id)
    );
    """)
    
    conn.commit()
    conn.close()
    print("✅ SQLite 뉴스 및 회원/즐겨찾기 테이블 초기화 완료!")

def save_to_database(title, published_at, summaries, original_url):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT OR IGNORE INTO news (title, published_at, summary_1, summary_2, summary_3, original_url)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (title, published_at, summaries[0], summaries[1], summaries[2], original_url))
        conn.commit()
        if cursor.rowcount > 0:
            print("💾 [DB 성공] 데이터베이스에 안전하게 저장되었습니다.")
            return True
        else:
            print("🛑 [DB 패스] 이미 존재하는 중복 URL 기사입니다.")
            return False
    except Exception as e:
        print(f"❌ DB 저장 오류: {e}")
        return False
    finally:
        conn.close()

def get_latest_news(limit=10):
    """리액트 전송용: 최신 뉴스 목록 및 3줄 요약 조회"""
    conn = sqlite3.connect(DB_PATH)
    # 딕셔너리 형태로 결과를 반환받아 JSON 변환을 쉽게 만듦
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, title, published_at, summary_1, summary_2, summary_3, original_url, category 
        FROM news 
        ORDER BY id DESC 
        LIMIT ?
    """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    # 리스트 안의 딕셔너리 형태로 변환
    return [dict(row) for row in rows]

if __name__ == "__main__":
    init_db()