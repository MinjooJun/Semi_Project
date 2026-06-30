# db_handler.py, scraper.py, summarize.py로 쪼개 놓은 모듈들을 import하여
# 전체 수집 -> 요약 -> 저장 프로세스를 유기적으로 컨트롤하는 메인 가동 스크립트

import time
from apscheduler.schedulers.background import BackgroundScheduler
from utils.scraper import fetch_naver_news_links, extract_article_text
from utils.summarizer import summarize_news_with_ollama
from database.db_handler import init_db, save_to_database

def start_pipeline(keyword, count=5):
    print(f"🔎 '{keyword}' 관련 실시간 뉴스 파이프라인 가동 시작...\n")
    
    # 1. DB 테이블 초기화 검사
    init_db()
    print("="*50)
    
    # 2. 뉴스 링크 수집
    news_items = fetch_naver_news_links(keyword, display_count=count)
    
    for i, item in enumerate(news_items, 1):
        title = item['title'].replace("<b>", "").replace("</b>", "")
        url = item['link']
        pub_date = item['pubDate']
        
        print(f"\n[{i}] 제목: {title}")
        
        # 3. 본문 추출
        print("🔄 1단계: 고도화된 본문 데이터 추출 중...")
        content = extract_article_text(url)
        
        if not content or len(content) < 150:
            print("⚠️ 본문 내용이 부실하거나 추출에 최종 실패하여 요약을 건너뜁니다.")
            continue
            
        print(f"✅ 본문 {len(content)}자 확보 완료.")
        
        # 📍 (내일 예정) 여기에 2단계: '중복 뉴스 필터링' 로직이 끼어들 자리입니다.
        
        # 4. LLM 요약
        print("🔄 2단계: 로컬 AI 한국어 3줄 요약 생성 중...")
        summaries = summarize_news_with_ollama(content)
        
        print("✨ [AI가 분석한 핵심 3줄 요약] ✨")
        for s in summaries:
            print(f"  └ {s}")
            
        # 5. DB 저장
        save_to_database(title, pub_date, summaries, url)
        print("="*50)

if __name__ == "__main__":
    # 테스트용 검색어 및 수집 개수 설정
    start_pipeline("인공지능", count=3)