import urllib.request
import urllib.parse
import json
import os
import re
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from newspaper import Article, Config
import ollama

# =========================================================================
# [NLTK 환경 에러 자동 우회 및 사전 다운로드]
# =========================================================================
import nltk
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    print("🔄 최초 실행: 자연어 처리(NLTK) 리소스를 다운로드합니다...")
    nltk.download('punkt')
    nltk.download('punkt_tab')


# =========================================================================
# 1. 환경 변수(.env) 로드 및 네이버 API 인증 정보 세팅
# =========================================================================
load_dotenv()

CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")
OLLAMA_MODEL = "llama3" 
DB_PATH = "news_database.db"

# 크롤링 차단(Anti-bot)을 우회하기 위한 브라우저 변장 헤더 정의
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# =========================================================================
# 2. SQLite DB 데이터 저장(INSERT) 함수
# =========================================================================
def save_to_database(title, url, pub_date, summary_list):
    """
    수집 및 요약이 완료된 뉴스 데이터를 SQLite DB 테이블에 안전하게 저장합니다.
    URL UNIQUE 제약조건을 이용해 중복 입력을 원천 차단합니다.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 3줄 요약 리스트 개수 방어 처리
    s1 = summary_list[0] if len(summary_list) > 0 else "요약 없음"
    s2 = summary_list[1] if len(summary_list) > 1 else "요약 없음"
    s3 = summary_list[2] if len(summary_list) > 2 else "요약 없음"
    
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO news_articles 
            (title, original_url, published_at, extracted_at, summary_1, summary_2, summary_3)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (title, url, pub_date, current_time, s1, s2, s3))
        
        conn.commit()
        if cursor.rowcount > 0:
            print("💾 [DB 성공] 데이터베이스에 안전하게 저장되었습니다.")
        else:
            print("🛑 [DB 패스] 이미 데이터베이스에 존재하는 중복 URL 기사입니다.")
            
    except Exception as e:
        print(f"❌ DB 저장 중 에러 발생: {e}")
    finally:
        conn.close()

# 일부러 에러 유도 테스트용 코드
def test_error_injection(url):
    if "error_test" in url:
        raise Exception("🚨 강제 장애 발생: 사이트 구조 변경 테스트")

# =========================================================================
# 3. 본문 추출 핵심 함수 (네이버 뉴스 전용 로직 + 일반 언론사 이원화)
# =========================================================================
def extract_article_text(url):
    if "naver.com" in url:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            html = urllib.request.urlopen(req).read()
            soup = BeautifulSoup(html, 'html.parser')
            
            for tag_id in ['dic_area', 'newsct_article', 'articeBody']:
                article_body = soup.find(['article', 'div'], id=tag_id)
                if article_body:
                    text = article_body.get_text().strip()
                    return re.sub(r'\s+', ' ', text)
        except Exception as e:
            print(f"❌ 네이버 자체 본문 파싱 실패: {e}")
            
    try:
        config = Config()
        config.browser_user_agent = USER_AGENT
        config.request_timeout = 15
        config.memoize_articles = False
        config.fetch_images = False
        
        article = Article(url, language='ko', config=config)
        article.download()
        article.parse()
        text_content = article.text.strip()
        
        if len(text_content) < 150:
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            html = urllib.request.urlopen(req).read()
            soup = BeautifulSoup(html, 'html.parser')
            for class_name in ['article_body', 'article_content', 'news_body', 'story-news', 'articleBody']:
                backup_body = soup.find('div', class_=lambda x: x and any(c in x for c in [class_name]))
                if backup_body and len(backup_body.get_text().strip()) > 150:
                    return backup_body.get_text().strip()
                    
        return text_content
    except Exception as e:
        print(f"❌ 일반 언론사 본문 파싱 실패: {e}")
    return None

# =========================================================================
# 4. 로컬 Ollama 한국어 3줄 요약 함수 (format="json" 옵션 적용)
# =========================================================================
def summarize_news_with_ollama(title, content):
    """
    Ollama 로컬 LLM의 하드웨어 JSON 강제 옵션(format='json')을 사용하여
    에러율 0%의 한국어 3줄 요약 데이터를 추출합니다.
    """
    prompt = f"""
    당신은 대한민국 최고의 뉴스 요약 전문가입니다. 제공된 뉴스 제목과 본문을 바탕으로 핵심 내용 3줄 요약을 작성하세요.
    
    [엄격 규칙]
    1. 모든 요약 문장은 반드시 '한국어(Korean)'로만 작성해야 합니다. 절대 영어로 번역하지 마십시오.
    2. 반드시 아래의 JSON 스키마 규격을 완벽히 준수하여 응답하십시오.

    뉴스 제목: {title}
    뉴스 본문: {content}

    [JSON 반환 형식]
    {{
        "summary": [
            "1번째 핵심 요약 문장 (한국어로 작성)",
            "2번째 핵심 요약 문장 (한국어로 작성)",
            "3번째 핵심 요약 문장 (한국어로 작성)"
        ]
    }}
    """
    
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            format="json",  # 무조건 지정된 포맷의 깨끗한 JSON만 반환하도록 하드웨어 레벨에서 규제
            options={"temperature": 0.1}
        )
        
        result_text = response['message']['content'].strip()
        result_json = json.loads(result_text)
        return result_json.get("summary", ["요약본 파싱 실패", "규격 오류", "데이터 확인 필요"])
        
    except Exception as e:
        print(f"❌ Ollama 요약 연산 또는 파싱 최종 실패: {e}")
        return ["뉴스 요약 실패", "오류 발생", "체크 필요"]

# =========================================================================
# 5. 네이버 뉴스 API 검색 요청 함수
# =========================================================================
def search_naver_news(keyword, display_count=5):
    encText = urllib.parse.quote(keyword)
    url = f"https://openapi.naver.com/v1/search/news.json?query={encText}&display={display_count}&sort=date"
    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", CLIENT_ID)
    request.add_header("X-Naver-Client-Secret", CLIENT_SECRET)
    try:
        response = urllib.request.urlopen(request)
        if response.getcode() == 200: return json.loads(response.read().decode('utf-8'))
    except Exception as e: print(f"🚨 API 요청 오류: {e}")
    return None

# =========================================================================
# 6. 메인 파이프라인 가동 루프
# =========================================================================
if __name__ == "__main__":
    search_keyword = "인공지능"
    target_count = 3  
    
    print(f"🔎 '{search_keyword}' 관련 최신 뉴스 수집 및 파이프라인 가동...\n")
    news_data = search_naver_news(search_keyword, display_count=target_count)
    
    if news_data and 'items' in news_data:
        for idx, item in enumerate(news_data['items']):
            print(f"[{idx+1}] ==================================================")
            clean_title = item['title'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"')
            print(f"제목: {clean_title}")
            
            print("🔄 1단계: 본문 데이터 추출 중...")
            article_text = extract_article_text(item['link'])
            
            # 테스트를 위해 글자 수 제한 조건을 50자로 여유 있게 설정
            if article_text and len(article_text) > 50:
                print(f"✅ 본문 {len(article_text)}자 확보 완료. 2단계: AI 3줄 요약 생성 중...")
                summary_list = summarize_news_with_ollama(clean_title, article_text)
                
                print("\n✨ [AI가 분석한 핵심 3줄 요약] ✨")
                for i, line in enumerate(summary_list):
                    print(f" └ {i+1}. {line}")
                
                # SQLite 저장 호출
                save_to_database(clean_title, item['link'], item['pubDate'], summary_list)
                print()
            else:
                print("⚠️ 본문 내용이 부실하거나 추출에 최종 실패하여 요약을 건너뜁니다.\n")