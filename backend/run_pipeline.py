# run_pipeline.py
import time
import html
import re
from datetime import datetime

# ⚠️ fetch_article 이 본문+이미지를 한 번에 가져오므로
#    extract_article_text / get_news_image 는 여기서 임포트하지 않습니다.
from utils.scraper import fetch_naver_news_links, fetch_article, pick_article_url
from utils.summarizer import summarize_news_with_ollama
from utils.filter import remove_batch_duplicates, is_duplicate_summary
from utils.classifier import predict_category, is_published_today
from utils.trend_explorer import get_dynamic_keywords
from database.db_handler import init_db, save_to_database

# 👇 데일리 요약은 daily_job.py 한 곳에서만 관리합니다
from daily_job import generate_daily_news_summary

SEP = "|"


def _normalize_labels(labels):
    """predict_category 결과 정리: 레거시 '사회' 보정, 중복 제거, 최소 1개 보장."""
    if isinstance(labels, str):
        labels = [x for x in labels.split(SEP) if x]
    out = []
    for lab in labels:
        lab = "사회/세계" if lab == "사회" else lab
        if lab and lab not in out:
            out.append(lab)
    return out or ["사회/세계"]


def clean_api_title(raw_title):
    """네이버 검색 API 제목의 <b> 태그, &quot; 등 HTML 노이즈 정제."""
    if not raw_title:
        return ""
    cleaned = re.sub(r"</?b>", "", raw_title)
    return html.unescape(cleaned).strip()


def total_news_pipeline_job():
    """
    [실시간 수집 파이프라인]
    수집 → 턴 내 제목 중복 병합 → 본문 추출 → 분류 → 요약 → 턴 내 요약 중복 → 적재

    ※ 중복 검사는 '이번 턴 안에서만' 수행합니다 (설계 의도).
      DB 과거 기사와의 유사도 비교는 하지 않습니다.
      단, 완전히 동일한 URL은 DB 유니크 인덱스가 물리적으로 막습니다.
    """
    init_db()
    print("\n🔍 실시간 이슈 수집을 시작합니다...")

    search_keywords = get_dynamic_keywords()
    all_raw_news = []
    for keyword in search_keywords:
        print(f"📡 수집 중: {keyword}")
        all_raw_news.extend(fetch_naver_news_links(keyword, display_count=5))

    if not all_raw_news:
        print("📭 수집된 기사가 없습니다.")
        return

    # [1차 필터] 제목 유사도 — 공짜. 대놓고 같은 기사는 여기서 병합됨
    unique_news = remove_batch_duplicates(all_raw_news)
    print(f"📦 원본 {len(all_raw_news)}건 → 턴 내 병합 후 {len(unique_news)}건")

    turn_summaries = []   # 이번 턴에 만든 요약들 (2차 필터용, DB와는 무관)
    saved, skipped = 0, 0

    for item in unique_news:
        try:
            title = clean_api_title(item.get("title", ""))
            if not title:
                continue

            if not is_published_today(item.get("pubDate", "")):
                skipped += 1
                continue

            # 스포츠/연예 링크는 JS 렌더링이라 언론사 원문으로 우회
            url = pick_article_url(item)

            # 본문과 대표 이미지를 HTTP 요청 '한 번'으로 함께 확보
            text, image_url = fetch_article(url, title=title)
            if not text:
                print(f"Skip ➔ 본문 추출 실패: {title[:25]}...")
                skipped += 1
                continue

            categories = _normalize_labels(predict_category(title, text))

            summaries = summarize_news_with_ollama(text, title=title)
            if not summaries:
                print(f"Skip ➔ 요약 생성 실패: {title[:25]}...")
                skipped += 1
                continue

            # [2차 필터] 요약문 유사도 — 제목 표현이 달라도 알맹이가 같으면 여기서 잡힘
            #  예: "손흥민 LAFC 복귀" vs "토트넘 떠난 손흥민, 미국행"
            #  제목 char n-gram으론 원리상 못 잡는 케이스를 담당합니다.
            if is_duplicate_summary(summaries[0], turn_summaries, threshold=0.75):
                print(f"Skip ➔ 턴 내 동일 사건: {title[:25]}...")
                skipped += 1
                continue

            ok = save_to_database(
                title=title,
                published_at=item.get("pubDate", ""),
                summaries=summaries,
                original_url=item.get("link", url),
                category=categories,
                image_url=image_url,          # 👈 fetch_article 이 이미 가져온 값 재사용
                report_count=item.get("report_count", 1),
            )

            if ok:
                turn_summaries.append(summaries[0])
                saved += 1
                cnt = item.get("report_count", 1)
                badge = f" ({cnt}곳 보도)" if cnt > 1 else ""
                print(f"💾 적재 [{SEP.join(categories)}]{badge} {title[:28]}...")
            else:
                skipped += 1

            time.sleep(0.3)

        except Exception as e:
            print(f"❌ 처리 중 오류: {e}")

    print(f"\n✅ 수집 완료 — 저장 {saved}건 / 스킵 {skipped}건")


if __name__ == "__main__":
    print("📢 [시스템 가동] 실시간 뉴스 AI 요약 파이프라인 수집기를 시작합니다.")
    print("🎯 매시 '정각(00분)' 및 '30분'에 자동 수집합니다.")
    print("💡 'Ctrl + C'를 누르면 즉시 종료됩니다!\n")

    DAILY_HOUR = 7
    DAILY_MINUTE = 13

    # ⚠️ 예전 방식(done 플래그 + second == 0)은 수집이 1분 넘게 걸리면
    #    리셋 구간(:01/:31)을 지나쳐버려 다음 슬롯이 통째로 스킵됐습니다.
    #    "이 슬롯을 이미 돌았는가"를 문자열 키로 기억하는 방식으로 교체합니다.
    last_pipeline_slot = None
    last_daily_date = None

    try:
        while True:
            now = datetime.now()

            if now.minute in (0, 30):
                slot = f"{now:%Y-%m-%d %H}:{now.minute}"
                if slot != last_pipeline_slot:
                    last_pipeline_slot = slot
                    print(f"\n⏰ [{now:%H:%M:%S}] 정기 수집 시작!")
                    total_news_pipeline_job()
                    print("💤 다음 타이밍까지 대기합니다...")

            if now.hour == DAILY_HOUR and now.minute == DAILY_MINUTE:
                today = f"{now:%Y-%m-%d}"
                if today != last_daily_date:
                    last_daily_date = today
                    print(f"\n🌅 [{now:%H:%M:%S}] 데일리 요약 실행!")
                    generate_daily_news_summary()

            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 사용자 종료(Ctrl+C). 파이프라인을 정상 종료합니다.")
