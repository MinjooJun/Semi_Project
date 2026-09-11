# daily_job.py
import json
from datetime import datetime
from collections import Counter

from database.db_handler import get_news_from_yesterday, save_daily_summary
from utils.cluster import cluster_news_groups
from utils.summarizer import summarize_cluster_brief

TOP_N = 10


def generate_daily_news_summary():
    """
    [데일리 뉴스 TOP 10 종합 요약기 - 통합 완결판]
    어제 적재된 뉴스를 군집별로
    다수결 카테고리 + 130자 핵심 요약을 만들어 단일 행으로 저장합니다.
    """
    print("\n" + "=" * 60)
    print(f"🌅 [Daily Job 가동] 어제자 뉴스 TOP {TOP_N} 종합 분석을 시작합니다...")
    print("=" * 60)

    # 1. 어제 뉴스 로드
    news_list = get_news_from_yesterday()
    if not news_list:
        print("📭 어제 수집된 뉴스가 없습니다. 작업을 종료합니다.")
        return

    print(f"📦 총 {len(news_list)}건을 대상으로 이슈 트래킹을 시작합니다.")

    # 2. 군집 '그룹 통째로' 받기
    try:
        groups = cluster_news_groups(news_list, n_clusters=TOP_N)
    except Exception as e:
        print(f"❌ K-Means 연산 중 오류: {e}")
        return

    if not groups:
        print("⚠️ 유효한 이슈 군집이 없습니다.")
        return

    final_payload = []

    # 3. 군집별 카테고리 다수결 + 130자 요약
    for i, articles in enumerate(groups):
        if not articles:
            continue

        rep = articles[0]  # 군집 대표 기사(최신순 첫 기사)
        rep_title = rep.get('title', '주요 대형 이슈')
        print(f"\n🔮 [{i+1}/{len(groups)}] 대표: {rep_title[:25]}... (묶인 기사 {len(articles)}건)")

        # 3-1. 카테고리 다수결 (멀티라벨 대응: 'A|B' 를 쪼개서 개별 라벨로 집계)
        # ⚠️ Counter(['경제|IT/과학', '경제']) 처럼 통짜 문자열을 세면
        #    같은 '경제'가 서로 다른 항목으로 잡혀 집계가 깨집니다.
        label_counter = Counter()
        for a in articles:
            for lab in str(a.get('category') or '').split('|'):
                lab = lab.strip()
                if lab:
                    label_counter[lab] += 1

        if label_counter:
            ranked = label_counter.most_common()
            best = ranked[0][1]
            # 1위 득표의 절반 이상 받은 라벨은 함께 살림 (최대 2개)
            dominant = [lab for lab, c in ranked if c >= best * 0.5][:2] or [ranked[0][0]]
        else:
            dominant = ["사회/세계"]

        # 3-2. 130자 초압축 요약 (군집 전체를 재료로 투입)
        print("🤖 Ollama LLM 요약 생성 중...")
        brief = summarize_cluster_brief(articles, representative_title=rep_title)

        # 3-3. 프론트 규격 통일 스키마 (두 파일 필드의 합집합)
        final_payload.append({
            "rank": i + 1,
            "title": rep_title,
            "category": "|".join(dominant),
            "categories": dominant,        # 👈 리액트가 칩 여러 개 그리기 편하게
            "summary": brief.get("summary", ""),      # 👈 문자열 1개 (dict 아님!)
            "keyword": brief.get("keyword", ""),
            # 기사 개수가 아니라 보도 건수 합계 (12곳이 보도 = 12)
            "cluster_size": sum(int(a.get('report_count') or 1) for a in articles),
            "cluster_id": rep.get('cluster_id'),
            "original_url": rep.get('original_url'),
            "published_at": rep.get('published_at'),
            "image_url": rep.get('image_url'),
        })
        print(f"✅ 팩킹 완료 -> [{dominant}] {brief.get('summary', '')[:40]}...")

    # 4. 단일 행으로 저장
    if not final_payload:
        print("⚠️ 추출된 이슈가 없어 저장을 취소했습니다.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    try:
        save_daily_summary(
            title=f"{today}자 데일리 핵심 이슈 TOP {len(final_payload)}",
            summary_json_str=json.dumps(final_payload, ensure_ascii=False)
        )
        print("\n" + "=" * 60)
        print(f"🎉 [성공] {len(final_payload)}개 이슈 리포트가 DB에 적재되었습니다!")
        print("=" * 60)
    except Exception as e:
        print(f"❌ DB 적재 중 오류: {e}")


if __name__ == "__main__":
    generate_daily_news_summary()