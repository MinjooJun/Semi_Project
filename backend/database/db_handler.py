import sqlite3
from datetime import datetime, timedelta
import os
from collections import Counter
import re

# 기존 SQLite 파일 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "news_database.db")

# 멀티라벨 저장 구분자. category 컬럼엔 "경제|IT/과학" 형태로 저장한다.
SEP = "|"


def _normalize_category(category):
    """category 인자가 리스트든 문자열이든 'A|B' 문자열로 통일."""
    if category is None:
        return "사회/세계"
    if isinstance(category, (list, tuple)):
        labels = [str(c).strip() for c in category if str(c).strip()]
        return SEP.join(labels) if labels else "사회/세계"
    return str(category).strip() or "사회/세계"


def get_connection():
    """SQLite DB 연결 (동시성 방어 timeout 설정)"""
    return sqlite3.connect(DB_PATH, timeout=20.0)


def init_db():
    """[DB 초기화] 시스템 테이블 생성"""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. 뉴스 테이블 (category 는 'A|B' 형태의 멀티라벨 문자열)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            published_at TEXT,
            summary_1 TEXT,
            summary_2 TEXT,
            summary_3 TEXT,
            original_url TEXT,
            category TEXT,
            image_url TEXT
        );
    ''')

    # 2. 데일리 요약 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            summary_json TEXT,
            created_at DATE DEFAULT (date('now', 'localtime'))
        );
    ''')

    # 3. 사용자 및 즐겨찾기 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            news_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, news_id)
        );
    ''')

    # [스키마 마이그레이션] 기존 DB에도 report_count 컬럼을 안전하게 추가
    # (이미 있으면 건너뜀 — 몇 번을 실행해도 안전합니다)
    cursor.execute("PRAGMA table_info(news)")
    existing_cols = [r[1] for r in cursor.fetchall()]
    if "report_count" not in existing_cols:
        cursor.execute("ALTER TABLE news ADD COLUMN report_count INTEGER DEFAULT 1")
        print("🔧 news 테이블에 report_count 컬럼을 추가했습니다.")

    # [중복 방어 최후의 보루] 완전히 동일한 URL 기사의 재적재 차단
    # ⚠️ 기존 DB에 중복 URL이 있으면 실패합니다 → 아래 주석의 청소 쿼리 참고
    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_news_url ON news(original_url);")
    except Exception as e:
        print(f"⚠️ URL 유니크 인덱스 생성 실패(기존 중복 데이터 존재): {e}")
        print("   해결: DELETE FROM news WHERE id NOT IN (SELECT MIN(id) FROM news GROUP BY original_url);")

    conn.commit()
    conn.close()


def save_to_database(title, published_at, summaries, original_url,
                     category="사회/세계", image_url=None, report_count=1):
    """
    [뉴스 저장] category 는 리스트(['경제','IT/과학']) 또는 문자열('경제|IT/과학') 모두 허용.
    report_count: 이번 턴에 같은 사건으로 병합된 기사 수 (이슈 랭킹의 가중치)
    """
    category = _normalize_category(category)

    conn = get_connection()
    cursor = conn.cursor()
    try:
        s1 = summaries[0] if len(summaries) > 0 else ""
        s2 = summaries[1] if len(summaries) > 1 else ""
        s3 = summaries[2] if len(summaries) > 2 else ""

        cursor.execute("""
            INSERT INTO news (title, published_at, summary_1, summary_2, summary_3,
                              original_url, category, image_url, report_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (title, published_at, s1, s2, s3, original_url, category, image_url,
              int(report_count or 1)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # URL 유니크 인덱스에 걸림 = 이미 있는 기사. 정상 동작이므로 조용히 넘어감.
        return False
    except Exception as e:
        print(f"❌ DB 저장 오류: {e}")
        return False
    finally:
        conn.close()

def get_recent_titles(limit=50):
    """[파이프라인 필수] 최근 수집된 뉴스 제목 리스트 반환 (중복 제거용)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM news ORDER BY id DESC LIMIT ?", (limit,))
    titles = [row[0] for row in cursor.fetchall()]
    conn.close()
    return titles


def get_latest_news(limit=50):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM news ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_news_from_yesterday():
    yesterday_dt = datetime.now() - timedelta(days=1)
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    naver_date_str = f"{yesterday_dt.day:02d} {months[yesterday_dt.month - 1]} {yesterday_dt.year}"
    iso_date_str = yesterday_dt.strftime("%Y-%m-%d")

    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM news WHERE published_at LIKE ? OR published_at LIKE ?",
                   (f"%{naver_date_str}%", f"%{iso_date_str}%"))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_daily_summary(title, summary_json_str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM daily_summary WHERE created_at = date('now', 'localtime')")
    cursor.execute("INSERT INTO daily_summary (title, summary_json) VALUES (?, ?)", (title, summary_json_str))
    conn.commit()
    conn.close()


def get_daily_summary():
    """최신 데일리 요약 조회"""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM daily_summary ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_daily_summary_by_date(target_date_str):
    """특정 날짜(YYYY-MM-DD) 데일리 요약 조회"""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM daily_summary WHERE created_at = ?", (target_date_str,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_realtime_trend_keywords(limit_news=300, top_n=10):
    """[실시간 트렌드] 최근 뉴스 제목에서 키워드 빈도 분석"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM news ORDER BY id DESC LIMIT ?", (limit_news,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return []

    all_words = []
    stop_words = {'뉴스', '기사', '오늘', '내일', '오전', '오후', '단독', '포토', '종합', '출시', '개최', '선정', '진행'}

    for row in rows:
        clean_text = re.sub(r'[^가-힣a-zA-Z0-9\s]', ' ', row[0])
        for word in clean_text.split():
            if 1 < len(word) <= 5 and word not in stop_words:
                all_words.append(word)

    word_counts = Counter(all_words)
    return [{"rank": i + 1, "keyword": word, "count": count}
            for i, (word, count) in enumerate(word_counts.most_common(top_n))]


# [사용자 및 즐겨찾기 함수들...]
def check_user_exists(username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?;", (username,))
    user = cursor.fetchone()
    conn.close()
    return user is not None


def get_or_create_user(username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username = ?;", (username,))
    user = cursor.fetchone()
    if user:
        user_id = user[0]
    else:
        cursor.execute("INSERT INTO users (username) VALUES (?);", (username,))
        user_id = cursor.lastrowid
        conn.commit()
    conn.close()
    return user_id


def toggle_favorite_in_db(user_id, news_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM favorites WHERE user_id = ? AND news_id = ?;", (user_id, news_id))
    fav = cursor.fetchone()
    if fav:
        cursor.execute("DELETE FROM favorites WHERE user_id = ? AND news_id = ?;", (user_id, news_id))
        status = "removed"
    else:
        cursor.execute("INSERT INTO favorites (user_id, news_id) VALUES (?, ?);", (user_id, news_id))
        status = "added"
    conn.commit()
    conn.close()
    return status

def get_favorites_by_user(user_id):
    """
    [즐겨찾기 목록] 특정 사용자가 하트 누른 뉴스의 '전체 정보'를 최신 등록순으로 반환.
    favorites 테이블엔 news_id만 있으므로 news 테이블과 JOIN해서 제목/요약/이미지를 붙여옵니다.
    """
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.*, f.created_at AS favorited_at
        FROM favorites f
        JOIN news n ON n.id = f.news_id
        WHERE f.user_id = ?
        ORDER BY f.id DESC;
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_favorite_ids_by_user(user_id):
    """
    [하트 채우기용] 즐겨찾기한 news_id 숫자 배열만 가볍게 반환.
    뉴스 리스트 화면에서 '어떤 카드에 하트를 칠할지' 판단할 때 씁니다.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT news_id FROM favorites WHERE user_id = ?;", (user_id,))
    ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    return ids


def news_exists(news_id):
    """[방어용] 존재하지 않는 news_id가 favorites에 박히는 것을 막습니다."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM news WHERE id = ?;", (news_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists