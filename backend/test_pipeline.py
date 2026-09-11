# backend/test_pipeline.py
"""
뉴스 파이프라인 통합 테스트 스크립트.

실행 위치: backend/ 폴더 (run_pipeline.py 와 같은 위치)
    (.venv) PS ...\\backend> python test_pipeline.py

────────────────────────────────────────────────────────────────
[0단계] 환경 점검      — import / .env / Ollama / DB 스키마
[1단계] 오프라인 유닛  — 네트워크·Ollama 없이 즉시 검증
[2단계] 통합 테스트    — 아래 플래그를 True 로 켜야 실행됨 (실제 API/LLM 사용)
────────────────────────────────────────────────────────────────

⚠️ 기본값은 전부 False 입니다. 0~1단계만 먼저 돌려서 초록불 확인 후,
   필요한 플래그만 하나씩 켜세요. 위에서부터 순서대로 켜는 걸 권합니다.
"""

import os
import sys
import inspect
import sqlite3
from datetime import datetime, timedelta

# ===================== 통합 테스트 스위치 =====================
RUN_NAVER_API = False      # 네이버 검색 API 호출 (키 필요, 몇 초)
RUN_SCRAPE_ONE = False     # 기사 1건 본문+이미지 추출 (네트워크, 몇 초)
RUN_SUMMARIZE_ONE = False  # 기사 1건 LLM 3줄 요약 (Ollama, 20~60초)
RUN_FULL_TURN = False      # 수집 턴 1회 전체 실행 (API+Ollama, 10~40분!)
RUN_DAILY_JOB = True      # 데일리 요약 생성 (Ollama, 5~20분)
DAILY_JOB_DAYS_AGO = 1     # 0=오늘 / 1=어제. DB 초기화 직후엔 0으로.
# ==============================================================


# ---------- 검증 헬퍼 (assert 대신, 실패해도 계속 진행) ----------
_passed, _failed, _skipped = 0, 0, 0
_failures = []


def check(name, got, expected):
    global _passed, _failed
    ok = got == expected
    print(f"{'✅' if ok else '❌'} {name}")
    if not ok:
        print(f"     기대={expected!r}\n     실제={got!r}")
        _failed += 1
        _failures.append(name)
    else:
        _passed += 1


def check_true(name, got):
    check(name, bool(got), True)


def info(name, value):
    print(f"ℹ️  {name}: {value}")


def skip(name, why):
    global _skipped
    _skipped += 1
    print(f"⏭️  {name} — {why}")


def section(title):
    print("\n" + "─" * 60)
    print(f"  {title}")
    print("─" * 60)


def _naver_date(dt):
    """네이버 pubDate 포맷 문자열 생성 (예: Tue, 14 Jul 2026 09:00:00 +0900)"""
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    return (f"{days[dt.weekday()]}, {dt.day:02d} {months[dt.month-1]} "
            f"{dt.year} {dt.hour:02d}:{dt.minute:02d}:00 +0900")


# =====================================================================
# 0단계: 환경 점검
# =====================================================================
def test_imports():
    """모든 모듈이 정상 import 되는지. 파일이 엉뚱하게 덮어써졌으면 여기서 걸린다."""
    section("0-1. 모듈 import 점검")

    targets = [
        ("utils.classifier", ["predict_category", "is_published_today",
                              "labels_to_str", "str_to_labels"]),
        ("utils.cluster", ["cluster_news_groups", "cluster_and_get_top_news", "_weight"]),
        ("utils.filter", ["clean_title", "find_duplicate_index", "is_duplicate_news",
                          "is_duplicate_summary", "remove_batch_duplicates"]),
        ("utils.scraper", ["fetch_naver_news_links", "fetch_article", "pick_article_url",
                           "is_junk_body", "strip_boilerplate"]),
        ("utils.summarizer", ["summarize_news_with_ollama", "summarize_cluster_brief",
                              "_trim_to_limit"]),
        ("utils.trend_explorer", ["get_dynamic_keywords"]),
        ("database.db_handler", ["init_db", "save_to_database", "get_latest_news"]),
        ("daily_job", ["generate_daily_news_summary"]),
    ]

    for mod_name, funcs in targets:
        try:
            mod = __import__(mod_name, fromlist=funcs)
            missing = [f for f in funcs if not hasattr(mod, f)]
            if missing:
                check(f"{mod_name} 필수 함수 존재", f"없음: {missing}", "전부 있음")
            else:
                check(f"{mod_name} import", True, True)
        except Exception as e:
            check(f"{mod_name} import", f"{type(e).__name__}: {e}", True)


def test_env():
    section("0-2. .env / 외부 서비스 점검")

    from dotenv import load_dotenv
    load_dotenv()

    cid = os.getenv("NAVER_CLIENT_ID")
    csec = os.getenv("NAVER_CLIENT_SECRET")
    check_true("NAVER_CLIENT_ID 존재", bool(cid))
    check_true("NAVER_CLIENT_SECRET 존재", bool(csec))

    # Ollama 살아있는지 (모델 목록 조회)
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        check_true("Ollama 응답", r.status_code == 200)
        info("설치된 모델", models or "(없음)")
        has_llama3 = any(m.startswith("llama3") for m in models)
        check_true("llama3 모델 존재", has_llama3)
        if not has_llama3:
            print("     💡 해결: 터미널에서  ollama pull llama3")
    except Exception as e:
        check("Ollama 연결", f"{type(e).__name__}", True)
        print("     💡 해결: 터미널에서  ollama serve")

    # KoNLPy 는 Java(JDK) 가 있어야 동작
    try:
        from konlpy.tag import Okt
        Okt().nouns("테스트 문장입니다")
        check("KoNLPy(Okt) 동작", True, True)
    except Exception as e:
        check("KoNLPy(Okt) 동작", f"{type(e).__name__}: {str(e)[:60]}", True)
        print("     💡 JDK 미설치 의심 → trend_explorer 가 폴백 키워드로만 돕니다")


def test_db_schema():
    """report_count 컬럼 / URL 유니크 인덱스가 실제로 적용됐는지."""
    section("0-3. DB 스키마 점검")

    from database.db_handler import init_db, DB_PATH
    init_db()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(news)")
    cols = [r[1] for r in cur.fetchall()]
    check_true("news.report_count 컬럼 존재", "report_count" in cols)

    cur.execute("PRAGMA index_list(news)")
    indexes = [r[1] for r in cur.fetchall()]
    check_true("URL 유니크 인덱스(idx_news_url) 존재", "idx_news_url" in indexes)
    if "idx_news_url" not in indexes:
        print("     💡 기존 DB에 중복 URL이 있으면 생성이 실패합니다. 아래 실행 후 재시도:")
        print("        DELETE FROM news WHERE id NOT IN (SELECT MIN(id) FROM news GROUP BY original_url);")

    for t in ("news", "daily_summary", "favorites", "users"):
        try:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            info(f"{t} 행 수", cur.fetchone()[0])
        except sqlite3.OperationalError:
            info(f"{t}", "테이블 없음")

    # 안내문이 요약으로 저장된 쓰레기 행 (스크래퍼 수정 전 데이터)
    try:
        cur.execute("""
            SELECT COUNT(*) FROM news
            WHERE summary_1 LIKE '%오분류%' OR summary_1 LIKE '%아웃링크%'
               OR summary_1 LIKE '%자동 분류 시스템%'
               OR summary_1 LIKE '%요약 생성 중 일시적인%'
        """)
        junk = cur.fetchone()[0]
        if junk:
            print(f"🚨 안내문이 요약으로 저장된 행: {junk}개 → reset_db.py 검토 권장")
        else:
            check("쓰레기 요약 행 없음", True, True)
    except sqlite3.OperationalError:
        pass

    conn.close()


# =====================================================================
# 1단계: 오프라인 유닛 테스트
# =====================================================================
def test_clean_title():
    section("1-1. filter.clean_title — HTML 태그 제거")
    from utils.filter import clean_title

    a = clean_title("<b>삼성</b>전자 반도체 신기록")
    b = clean_title("삼성전자 <b>반도체</b> 신기록")
    check("태그 안 b 글자가 안 남음", "b" in a, False)
    check("<b> 위치만 다른 같은 제목이 동일하게 정제됨", a, b)
    check("한자 尹 → 윤 변환", "윤" in clean_title("尹 대통령 발언"), True)
    check("[단독] 말머리 제거", clean_title("[단독] 속보"), "속보")


def test_find_duplicate_index():
    section("1-2. filter.find_duplicate_index — 중복 위치 반환")
    from utils.filter import find_duplicate_index, is_duplicate_news

    seen = ["코스피 3000 돌파", "<b>삼성</b>전자 반도체 신기록"]

    check("같은 기사(태그 위치만 다름) → 인덱스 1",
          find_duplicate_index("삼성전자 <b>반도체</b> 신기록", seen), 1)
    check("전혀 다른 기사 → -1",
          find_duplicate_index("오늘 서울 날씨 맑음", seen), -1)
    check("빈 리스트 → -1", find_duplicate_index("아무거나", []), -1)
    check("호환용 is_duplicate_news 도 동작",
          is_duplicate_news("삼성전자 <b>반도체</b> 신기록", seen), True)


def test_remove_batch_duplicates_counts():
    section("1-3. filter.remove_batch_duplicates — 병합 + report_count 집계")
    from utils.filter import remove_batch_duplicates

    items = [
        {"title": "<b>최저임금</b> 1만700원 결정", "link": "1"},
        {"title": "최저임금 <b>1만700원</b> 결정", "link": "2"},   # 위와 중복
        {"title": "최저임금 1만700원 결정...", "link": "3"},        # 위와 중복
        {"title": "오늘 서울 날씨 맑고 덥겠습니다", "link": "4"},
    ]
    result = remove_batch_duplicates(items)

    check("4건 중 중복 병합되어 2건 남음", len(result), 2)
    check("대표 기사의 report_count = 3 (3곳 보도)",
          result[0].get("report_count"), 3)
    check("단독 기사의 report_count = 1",
          result[1].get("report_count"), 1)
    check("병합돼도 대표는 '첫 번째' 기사", result[0]["link"], "1")


def test_is_published_today():
    section("1-4. classifier.is_published_today — 오늘/어제 판별")
    from utils.classifier import is_published_today

    check("오늘 날짜 기사 → True", is_published_today(_naver_date(datetime.now())), True)
    check("어제 날짜 기사 → False",
          is_published_today(_naver_date(datetime.now() - timedelta(days=1))), False)
    check("빈 문자열 → False", is_published_today(""), False)
    check("쓰레기 문자열 → False", is_published_today("어제쯤?"), False)


def test_predict_category():
    section("1-5. classifier.predict_category — 멀티라벨 반환")
    from utils.classifier import predict_category, labels_to_str, str_to_labels

    labels = predict_category("코스피 3000 돌파, 반도체주 급등", "삼성전자와 SK하이닉스가 상승했다.")
    check("반환 타입이 list", isinstance(labels, list), True)
    check("최소 1개 라벨 보장", len(labels) >= 1, True)
    info("예측 결과", labels)

    check("labels_to_str", labels_to_str(["경제", "IT/과학"]), "경제|IT/과학")
    check("str_to_labels", str_to_labels("경제|IT/과학"), ["경제", "IT/과학"])
    check("빈 문자열 → 빈 리스트", str_to_labels(""), [])


def test_cluster_ranking():
    section("1-6. cluster — report_count 기반 랭킹")
    from utils.cluster import cluster_news_groups, cluster_and_get_top_news, _weight

    check("_weight: report_count 없으면 1", _weight({}), 1)
    check("_weight: None 이면 1", _weight({"report_count": None}), 1)
    check("_weight: 정상값", _weight({"report_count": 7}), 7)

    # 대형 이슈(표 5개짜리 3건) vs 무명 기사(표 1개짜리 10건)
    news = ([{"title": f"최저임금 인상 결정 {i}", "report_count": 5} for i in range(3)]
            + [{"title": f"무명 기사 제목 {i}", "report_count": 1} for i in range(10)])

    groups = cluster_news_groups(news, n_clusters=3)
    weights = [sum(_weight(a) for a in g) for g in groups]
    info("군집별 보도량 합계", weights)
    check("보도량 내림차순 정렬", weights == sorted(weights, reverse=True), True)
    check("cluster_id 부여됨", all("cluster_id" in n for n in news), True)

    # 기사 수 < 군집 수인 경로 (수집 초기 / 주말)
    few = [{"title": "A", "report_count": 1},
           {"title": "B", "report_count": 9},
           {"title": "C", "report_count": 3}]
    g2 = cluster_news_groups(few, n_clusters=10)
    check("기사 부족 시에도 report_count 순 정렬",
          [grp[0]["title"] for grp in g2], ["B", "C", "A"])
    check("기사 부족 시에도 cluster_id 부여",
          all("cluster_id" in n for n in few), True)

    check("cluster_and_get_top_news 는 납작한 리스트",
          all(isinstance(x, dict) for x in cluster_and_get_top_news(news, 3)), True)


def test_scraper_junk_filter():
    section("1-7. scraper — 안내문 판별 (손흥민 버그 방어벽)")
    from utils.scraper import is_junk_body, strip_boilerplate, pick_article_url

    # 실제로 DB에 저장됐던 그 안내문
    junk_text = ("네이버스포츠가 언론사 분류와 기술 기반의 자동 분류 시스템을 사용하여 "
                 "스포츠 기사 섹션 정보를 제공합니다. 오분류 제보는 네이버스포츠로 "
                 "제보를 부탁드립니다. 언론사 페이지(아웃링크)로 이동해 볼 수 있습니다. "
                 "개별 기사의 섹션 정보는 해당 언론사의 분류를 따릅니다. " * 3)
    title = "손흥민, LAFC 복귀…LA 갤럭시와 엘 트라피코로 시즌 재개"

    junk, reason = is_junk_body(junk_text, title)
    check("안내문을 본문으로 인정하지 않음", junk, True)
    info("차단 사유", reason)

    real_body = ("손흥민이 LAFC 복귀전을 치른다. 손흥민은 LA 갤럭시와의 엘 트라피코 "
                 "더비에서 시즌 재개를 알린다. LAFC는 이번 경기에서 승점 3점을 노린다. "
                 "손흥민은 지난 시즌 12골을 기록했다. " * 4)
    junk2, reason2 = is_junk_body(real_body, title)
    check("진짜 본문은 통과", junk2, False)

    check("짧은 본문 차단", is_junk_body("짧음", title)[0], True)
    check("빈 본문 차단", is_junk_body("", title)[0], True)

    # 제목-본문 일치도: 제목과 전혀 무관한 긴 텍스트
    unrelated = "오늘 날씨는 맑고 기온은 섭씨 30도까지 오르겠습니다. " * 20
    check("제목과 무관한 본문 차단", is_junk_body(unrelated, title)[0], True)

    check("저작권 문구 제거",
          "무단전재" in strip_boilerplate("본문입니다. 무단전재 및 재배포 금지"), False)
    check("기자 이메일 제거",
          "@" in strip_boilerplate("기사 끝. hong@news.co.kr"), False)

    # 스포츠 링크는 언론사 원문으로 우회해야 함
    item = {"link": "https://m.sports.naver.com/article/123",
            "originallink": "https://news.chosun.com/article/456"}
    check("스포츠 링크 → originallink 우회",
          pick_article_url(item), "https://news.chosun.com/article/456")
    normal = {"link": "https://n.news.naver.com/article/1", "originallink": "https://x.com/1"}
    check("일반 링크는 link 그대로",
          pick_article_url(normal), "https://n.news.naver.com/article/1")


def test_summarizer_trim():
    section("1-8. summarizer — 130자 절단 안전장치")
    from utils.summarizer import _trim_to_limit, _ensure_period, MAX_SUMMARY_LEN

    check("마침표 자동 부착", _ensure_period("문장입니다"), "문장입니다.")
    check("이미 마침표면 그대로", _ensure_period("문장입니다."), "문장입니다.")

    short = "짧은 요약입니다."
    check("짧은 문장은 그대로", _trim_to_limit(short), short)

    long_text = ("첫 번째 문장은 여기서 끝납니다. " * 3) + ("두 번째로 아주 긴 문장이 계속 이어집니다 " * 10)
    trimmed = _trim_to_limit(long_text)
    check(f"{MAX_SUMMARY_LEN}자 이내로 절단", len(trimmed) <= MAX_SUMMARY_LEN, True)
    info("절단 결과", f"{len(trimmed)}자 | {trimmed}")

    check("빈 입력 → 빈 문자열", _trim_to_limit(""), "")
    check("None 입력 → 빈 문자열", _trim_to_limit(None), "")


def test_db_normalize():
    section("1-9. db_handler — 카테고리 정규화")
    from database.db_handler import _normalize_category

    check("리스트 → 'A|B'", _normalize_category(["경제", "IT/과학"]), "경제|IT/과학")
    check("문자열은 그대로", _normalize_category("경제"), "경제")
    check("None → 기본값", _normalize_category(None), "사회/세계")
    check("빈 리스트 → 기본값", _normalize_category([]), "사회/세계")


def test_normalize_labels():
    section("1-10. run_pipeline._normalize_labels")
    from run_pipeline import _normalize_labels, clean_api_title

    check("레거시 '사회' → '사회/세계'", _normalize_labels(["사회"]), ["사회/세계"])
    check("중복 제거", _normalize_labels(["경제", "경제"]), ["경제"])
    check("빈 입력 → 기본값", _normalize_labels([]), ["사회/세계"])
    check("문자열 입력도 처리", _normalize_labels("경제|IT/과학"), ["경제", "IT/과학"])

    check("clean_api_title: <b> 제거",
          clean_api_title("<b>삼성</b>전자 신기록"), "삼성전자 신기록")
    check("clean_api_title: &quot; 언이스케이프",
          clean_api_title("&quot;위기&quot; 경고"), '"위기" 경고')


# =====================================================================
# 2단계: 통합 테스트 (플래그로 제어)
# =====================================================================
def test_trend_keywords():
    section("2-1. trend_explorer — 실시간 핫 키워드 (구글 RSS)")
    from utils.trend_explorer import get_dynamic_keywords

    kws = get_dynamic_keywords()
    check("키워드 리스트 반환", isinstance(kws, list) and len(kws) > 0, True)
    info("추출된 키워드", kws)

    fallback = {"정치", "경제", "IT/과학", "사회/세계", "문화/트렌드", "라이프"}
    if set(kws) == fallback:
        print("⚠️  폴백 키워드가 나왔습니다 → RSS 실패 또는 KoNLPy(JDK) 문제")
    else:
        check("폴백이 아닌 실제 트렌드", True, True)

    press = [k for k in kws if k in ("연합뉴스", "조선일보", "중앙일보", "한겨레", "동아일보", "뉴시스")]
    check("언론사명이 키워드로 안 섞임", press, [])
    return kws


def test_naver_api():
    section("2-2. 네이버 검색 API")
    from utils.scraper import fetch_naver_news_links

    items = fetch_naver_news_links("경제", display_count=3)
    check("기사 수신", len(items) > 0, True)
    if not items:
        print("     💡 .env 의 API 키 또는 네트워크를 확인하세요")
        return None

    it = items[0]
    check("title 필드 존재", "title" in it, True)
    check("link 필드 존재", "link" in it, True)
    check("pubDate 필드 존재", "pubDate" in it, True)
    check("originallink 필드 존재 (스포츠 우회에 필요)", "originallink" in it, True)
    info("첫 기사 제목", it.get("title", "")[:50])
    return items


def test_scrape_one(items=None):
    section("2-3. fetch_article — 본문 + 이미지 (요청 1회)")
    from utils.scraper import fetch_article, pick_article_url
    from run_pipeline import clean_api_title

    if not items:
        from utils.scraper import fetch_naver_news_links
        items = fetch_naver_news_links("경제", display_count=3)
    if not items:
        skip("본문 추출", "기사를 못 받아옴")
        return None, None

    for it in items:
        title = clean_api_title(it.get("title", ""))
        url = pick_article_url(it)
        text, image_url = fetch_article(url, title=title)
        info("시도한 URL", url[:70])
        if text:
            check("본문 추출 성공", True, True)
            info("본문 길이", f"{len(text)}자")
            info("본문 앞부분", text[:120] + "...")
            check("안내문이 안 섞임", "오분류 제보" in text, False)
            info("이미지 URL", (image_url or "(없음)")[:70])
            return text, title
        print("   → 이 기사는 추출 실패, 다음 기사 시도...")

    skip("본문 추출", "모든 후보 실패 (네이버 DOM 변경 의심)")
    return None, None


def test_summarize_one(text=None, title=""):
    section("2-4. summarize_news_with_ollama — 3줄 요약")
    from utils.summarizer import summarize_news_with_ollama

    if not text:
        text, title = test_scrape_one()
    if not text:
        skip("LLM 요약", "본문이 없음")
        return

    print("🤖 Ollama 요약 생성 중... (20~60초)")
    t0 = datetime.now()
    summaries = summarize_news_with_ollama(text, title=title)
    elapsed = (datetime.now() - t0).total_seconds()

    info("소요 시간", f"{elapsed:.1f}초")
    check("요약 리스트 반환", isinstance(summaries, list), True)
    check("3줄 이하", len(summaries) <= 3, True)

    if not summaries:
        print("⚠️  빈 리스트 반환 — Ollama 미실행이거나 LLM이 '기사 아님'으로 판단")
        return

    for i, s in enumerate(summaries, 1):
        print(f"   {i}) {s}")
    check("모든 문장이 마침표로 끝남",
          all(s.rstrip()[-1] in ".!?" for s in summaries if s), True)
    check("에러 문구가 저장되지 않음",
          any("오류가 발생" in s for s in summaries), False)

    # 3줄이 서로 다른 내용인지 (프롬프트 규칙 2번 검증)
    if len(summaries) >= 2:
        from utils.filter import _max_similarity
        sim = _max_similarity(summaries[0], [summaries[1]], ngram=(2, 3))
        info("1번-2번 문장 유사도", f"{sim:.2f} (낮을수록 좋음)")
        if sim > 0.7:
            print("   ⚠️  두 문장이 같은 말을 반복하는 것 같습니다")


def test_full_turn():
    section("2-5. 수집 턴 1회 전체 실행")
    print("⚠️  네이버 API + Ollama 를 모두 사용합니다. 10~40분 걸릴 수 있습니다.")

    from database.db_handler import get_latest_news
    from run_pipeline import total_news_pipeline_job

    before = len(get_latest_news(limit=1000))
    info("실행 전 DB 기사 수", before)

    t0 = datetime.now()
    total_news_pipeline_job()
    elapsed = (datetime.now() - t0).total_seconds()

    after_rows = get_latest_news(limit=1000)
    after = len(after_rows)
    info("실행 후 DB 기사 수", after)
    info("소요 시간", f"{elapsed/60:.1f}분")
    check("신규 기사가 적재됨", after > before, True)

    if after > before:
        newest = after_rows[0]
        info("최신 기사 제목", newest.get("title", "")[:50])
        info("카테고리", newest.get("category"))
        info("report_count", newest.get("report_count"))
        check("report_count 가 DB에 저장됨", newest.get("report_count") is not None, True)
        check("summary_1 이 비어있지 않음", bool(newest.get("summary_1")), True)
        check("요약에 안내문이 안 섞임",
              "오분류" in str(newest.get("summary_1", "")), False)


def test_daily_job():
    section(f"2-6. 데일리 요약 생성 (days_ago={DAILY_JOB_DAYS_AGO})")
    print("⚠️  Ollama 를 사용합니다. 5~20분 걸릴 수 있습니다.")

    import daily_job
    from database.db_handler import get_daily_summary

    # get_news_by_days_ago 패치를 적용했는지에 따라 호출 방식이 다름
    sig = inspect.signature(daily_job.generate_daily_news_summary)
    if "days_ago" in sig.parameters:
        daily_job.generate_daily_news_summary(days_ago=DAILY_JOB_DAYS_AGO)
    else:
        if DAILY_JOB_DAYS_AGO != 1:
            print("   ℹ️  days_ago 패치가 아직 없어 '어제' 기준으로 실행합니다.")
        daily_job.generate_daily_news_summary()

    row = get_daily_summary()
    if not row:
        print("⚠️  daily_summary 가 비어 있습니다.")
        print("     → 해당 날짜에 수집된 기사가 없거나, DB를 방금 초기화했을 수 있습니다.")
        print("     → DAILY_JOB_DAYS_AGO = 0 으로 바꿔 '오늘' 기준으로 시도해보세요.")
        skip("데일리 요약 검증", "저장된 결과 없음")
        return

    import json
    payload = json.loads(row["summary_json"])
    check("이슈가 1건 이상 생성됨", len(payload) > 0, True)
    info("생성된 이슈 수", len(payload))

    first = payload[0]
    for key in ("rank", "title", "category", "summary", "cluster_size"):
        check(f"필드 '{key}' 존재", key in first, True)

    check("summary 가 문자열 (dict 아님)", isinstance(first.get("summary"), str), True)
    check("summary 가 130자 이내", len(first.get("summary", "")) <= 130, True)

    sizes = [p.get("cluster_size", 0) for p in payload]
    info("이슈별 보도량", sizes)
    check("보도량 내림차순 (랭킹 정상)", sizes == sorted(sizes, reverse=True), True)

    print("\n📋 생성된 TOP 이슈:")
    for p in payload[:5]:
        print(f"   {p.get('rank')}. [{p.get('category')}] ({p.get('cluster_size')}건) "
              f"{str(p.get('title'))[:35]}")
        print(f"      → {p.get('summary')}")


# =====================================================================
# 실행부
# =====================================================================
def main():
    print("=" * 60)
    print("🧪 뉴스 파이프라인 통합 테스트")
    print(f"   실행 시각: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"   작업 폴더: {os.getcwd()}")
    print("=" * 60)

    # 0단계
    print("\n\n" + "█" * 60)
    print("  0단계: 환경 점검")
    print("█" * 60)
    test_imports()
    test_env()
    test_db_schema()

    # 1단계
    print("\n\n" + "█" * 60)
    print("  1단계: 오프라인 유닛 테스트 (네트워크/Ollama 불필요)")
    print("█" * 60)
    test_clean_title()
    test_find_duplicate_index()
    test_remove_batch_duplicates_counts()
    test_is_published_today()
    test_predict_category()
    test_cluster_ranking()
    test_scraper_junk_filter()
    test_summarizer_trim()
    test_db_normalize()
    test_normalize_labels()

    # 2단계
    any_integration = any([RUN_NAVER_API, RUN_SCRAPE_ONE, RUN_SUMMARIZE_ONE,
                           RUN_FULL_TURN, RUN_DAILY_JOB])
    if any_integration:
        print("\n\n" + "█" * 60)
        print("  2단계: 통합 테스트 (실제 API / LLM 사용)")
        print("█" * 60)

        items = None
        text, title = None, ""

        if RUN_NAVER_API:
            test_trend_keywords()
            items = test_naver_api()
        if RUN_SCRAPE_ONE:
            text, title = test_scrape_one(items)
        if RUN_SUMMARIZE_ONE:
            test_summarize_one(text, title)
        if RUN_FULL_TURN:
            test_full_turn()
        if RUN_DAILY_JOB:
            test_daily_job()
    else:
        print("\n\n⏭️  2단계 통합 테스트는 전부 꺼져 있습니다.")
        print("   파일 상단의 RUN_* 플래그를 True 로 바꿔 실행하세요.")
        print("   권장 순서: RUN_NAVER_API → RUN_SCRAPE_ONE → RUN_SUMMARIZE_ONE")
        print("              → RUN_FULL_TURN → RUN_DAILY_JOB")

    # 결과
    print("\n\n" + "=" * 60)
    print(f"  결과: ✅ {_passed}건 통과 / ❌ {_failed}건 실패 / ⏭️ {_skipped}건 스킵")
    print("=" * 60)
    if _failures:
        print("\n실패한 항목:")
        for f in _failures:
            print(f"  ❌ {f}")
        print()
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())