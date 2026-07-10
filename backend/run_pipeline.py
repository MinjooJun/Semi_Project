# db_handler.py, scraper.py, summarize.py로 쪼개 놓은 모듈들을 import하여
# 전체 수집 -> 요약 -> 저장 프로세스를 유기적으로 컨트롤하는 메인 가동 스크립트

import time
from apscheduler.schedulers.background import BackgroundScheduler
from utils.scraper import fetch_naver_news_links, extract_article_text
from utils.summarizer import summarize_news_with_ollama
from database.db_handler import init_db, save_to_database

<<<<<<< Updated upstream
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
=======
# 프로젝트 서브 모듈 간 유기적 임포트 완비
from utils.cluster import cluster_and_get_top_news
from utils.scraper import fetch_naver_news_links, extract_article_text, get_news_image
from utils.summarizer import summarize_news_with_ollama, summarize_cluster_5w1h
from utils.filter import is_duplicate_news, is_duplicate_summary
from classifier import predict_category
from database.db_handler import init_db, save_to_database, get_recent_titles, get_connection, get_news_from_yesterday, save_daily_summary


def clean_api_title(raw_title):
    """
    네이버 검색 API 결과 제목에 포함된 <b>, </b> 태그를 지우고,
    &quot;, &amp; 등의 HTML 노이즈 코드를 정상 문자로 완벽 정제합니다.
    """
    if not raw_title:
        return ""
    cleaned = re.sub(r'</?b>', '', raw_title)
    cleaned = html.unescape(cleaned)
    return cleaned.strip()


def start_pipeline(keyword, count=3):
    """단일 검색어 기반의 뉴스 수집-분류-요약 파이프라인 가동 엔진"""
    init_db()

    # 네이버 API를 통해 뉴스 가져오기
    news_items = fetch_naver_news_links(keyword, display_count=10)
    if not news_items:
        return

    seen_titles = get_recent_titles(limit=100)
    saved_count = 0

    for item in news_items:
        if saved_count >= count:
            break

        # 제목 HTML 태그 및 찌꺼기 완벽 제거
        clean_title = clean_api_title(item['title'])

        # 1차 제목 중복 체크
        if is_duplicate_news(clean_title, seen_titles):
            print(f"Skip ➔ 중복 차단: {clean_title[:20]}...")
            continue

        print(f"\n[{keyword} - {saved_count + 1}] 제목: {clean_title}")

        # 본문 추출 (text 변수명 일치)
        text = extract_article_text(item['link'])
        if not text or len(text) < 150:
            print("Skip ➔ 본문 글자 수 부족 (150자 미만)")
            continue

        image_url = get_news_image(item['link'])

        # 1.5단계: 머신러닝 카테고리 자동 추론
        category = predict_category(clean_title, text)
        print(f"🏷️ AI 모델 판정: [{category}]")

        # 2단계: 로컬 AI 3줄 요약 생성
        summaries = summarize_news_with_ollama(text)
        if not summaries or len(summaries) == 0:
            print("❌ 요약 생성 실패로 스킵")
            continue

        # 2.5단계: 요약문 기반 내용 중복 필터 (복사 기사 차단)
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT summary_1 FROM news ORDER BY id DESC LIMIT 50;")
            existing_summaries = [row[0]
                                  for row in cursor.fetchall() if row[0]]
            conn.close()
        except Exception:
            existing_summaries = []

        new_summary_1 = summaries[0]
        if is_duplicate_summary(new_summary_1, existing_summaries, threshold=0.75):
            print("Skip ➔ 요약 내용 중복 필터 걸림 (받아쓰기 기사)")
            continue

        if category == "사회":
            category = "사회/세계"
        # 3단계: 적재 완료 (정제된 깨끗한 제목 주입)
        save_to_database(
            title=clean_title,
            published_at=item['pubDate'],
            summaries=summaries,
            original_url=item['link'],
            category=category,
            image_url=image_url
        )
        print(f"💾 DB 적재 성공! (카테고리: {category})")

        seen_titles.append(clean_title)
        saved_count += 1
        time.sleep(0.3)


def total_news_pipeline_job():
    """마스터님이 엄선한 핵심 시사 키워드를 돌며 뉴스를 수집하는 메인 잡"""
    print(
        f"\n⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 실시간 뉴스 파이프라인 가동 시작...")

    # 💥 [키워드 고도화]: 현세의 맥락을 가장 잘 짚어주는 핫한 시사 핵심 단어셋
    search_keywords = [
        "대통령", "국회", "외교", "선거",
        "금리", "환율", "주식 폭락", "물가 불안", "반도체", "경기침체",
        "인공지능", "AI", "생성형", "우주항공", "로봇",
        "넷플릭스", "K팝", "트렌드", "사건사고", "검찰", "파업"
    ]

    for keyword in search_keywords:
        try:
            start_pipeline(keyword, count=2)
            time.sleep(0.5)
        except Exception as e:
            print(f"❌ [{keyword}] 수집 중 에러 패스: {e}")
            continue

    print("\n✅ 현재 주기의 수집 및 AI 요약 처리가 모두 완료되었습니다.")
    print("="*50)


def generate_daily_news_summary():
    """[스케줄러 내부 호출용 데일리 10대 이슈 육하원칙 종합 분석]"""
    print("\n" + "="*60)
    print("🌅 [데일리 요약 스케줄] 어제자 뉴스 종합 분석 작업을 시작합니다...")
    print("="*60)

    try:
        # 1. 어제 수집된 모든 뉴스 가져오기
        yesterday_news = get_news_from_yesterday()
        if not yesterday_news:
            print("⚠️ 어제 수집된 뉴스 데이터가 없어 데일리 요약을 생성하지 않습니다.")
            return

        print(f"📦 분석 대상 뉴스 개수: {len(yesterday_news)}개")

        # 2. 클러스터링 및 10대 대표 기사 추출
        top_news_list = cluster_and_get_top_news(yesterday_news, n_clusters=10)

        if not top_news_list:
            print("⚠️ 유효한 대표 이슈 기사가 추출되지 않았습니다.")
            return

        daily_summaries = []

        # 3. 각 대표 기사별 육하원칙 요약 생성
        for idx, news_item in enumerate(top_news_list, 1):
            print(f"✍️ 이슈 {idx} 육하원칙 요약 중... (제목: {news_item.get('title')})")

            # 군집 대표 기사 1개를 리스트에 담아 육하원칙 요약기 호출
            summary_5w1h = summarize_cluster_5w1h([news_item])

            summary_item = {
                "rank": idx,
                "title": news_item.get('title'),
                "summary": summary_5w1h,
                "cluster_id": news_item.get('cluster_id'),
                "original_url": news_item.get('original_url'),
                "published_at": news_item.get('published_at')
            }
            daily_summaries.append(summary_item)

        # 4. JSON 형태로 변환
        json_summary_str = json.dumps(daily_summaries, ensure_ascii=False)

        # [핵심 수정] db_handler의 규격에 맞춰 (대표 타이틀, JSON 문자열) 두 개를 넘겨줌
        main_title = f"🌅 어제자 뉴스 주요 이슈 TOP {len(daily_summaries)} 종합 분석"
        save_daily_summary(main_title, json_summary_str)

        print(f"🎉 데일리 뉴스 요약 (총 {len(daily_summaries)}개 이슈) DB 저장 완료!")

    except Exception as e:
        print(f"❌ 데일리 요약 생성 중 오류 발생: {e}")
>>>>>>> Stashed changes


if __name__ == "__main__":
<<<<<<< Updated upstream
    # 테스트용 검색어 및 수집 개수 설정
    start_pipeline("인공지능", count=3)
=======
    print("📢 [시스템 가동] 실시간 뉴스 AI 요약 파이프라인 수집기를 시작합니다.")
    print("🎯 본 프로그램은 매시 '정각(00분)' 및 '30분'에 자동으로 수집을 시작합니다.")
    print("💡 'Ctrl + C'를 누르면 지연 없이 즉시 완전히 꺼집니다!\n")

    # [설정] 데일리 뉴스 요약 실행 시간 지정 (24시간제)
    DAILY_HOUR = 9
    DAILY_MINUTE = 33

    # 중복 실행 방지 플래그
    daily_summary_done = False
    pipeline_job_done = False  # 정각/30분 중복 가동 방지용

    try:
        while True:
            now = datetime.now()

            # ---------------------------------------------------------
            # 1. [실시간 뉴스] 매시 정각(00분 00초) 또는 30분 00초에 실행
            # ---------------------------------------------------------
            if now.minute in [0, 30] and now.second == 0:
                if not pipeline_job_done:
                    print(
                        f"\n⏰ [{now.strftime('%H:%M:%S')}] 정기 뉴스 수집 타이밍 달성! 파이프라인을 가동합니다.")
                    total_news_pipeline_job()
                    pipeline_job_done = True  # 해당 분(Minute) 동안 중복 실행 방지
                    print(f"💤 수집 완료. 다음 정각 혹은 30분 타이밍까지 대기합니다...")

            # 01분이나 31분이 되면 다음 타이밍을 위해 플래그 초기화
            if now.minute in [1, 31]:
                pipeline_job_done = False

            # ---------------------------------------------------------
            # 2. [데일리 요약] 매일 아침 지정된 시간(07:55 00초)에 실행
            # ---------------------------------------------------------
            if now.hour == DAILY_HOUR and now.minute == DAILY_MINUTE and now.second == 0:
                if not daily_summary_done:
                    print(
                        f"\n🌅 [{now.strftime('%H:%M:%S')}] 데일리 요약 실행 시간이 되었습니다!")
                    generate_daily_news_summary()
                    daily_summary_done = True

            # 자정이 되면 데일리 요약 플래그 초기화 (다음날 다시 실행될 수 있도록)
            if now.hour == 0 and now.minute == 0:
                daily_summary_done = False

            # ---------------------------------------------------------
            # 3. [즉시 종료 대기] 1초마다 시계바늘을 보며 Ctrl+C를 체크
            # ---------------------------------------------------------
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 [종료 시그널 확인] 사용자가 종료(Ctrl+C)를 지시했습니다. 프로그램을 종료합니다.")
        print("👋 뉴스 백엔드 파이프라인이 정상 종료되었습니다.")
>>>>>>> Stashed changes
