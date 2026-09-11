# classifier.py  (멀티라벨 버전 - 기존 파일 그대로 덮어쓰기)
#
# 변경 요약
#   - predict_category() 반환값이 str -> list  (예: ['경제','IT/과학'])
#   - 학습이 MultiLabelBinarizer + OneVsRest(LinearSVC) 기반
#   - 규칙기반 fallback도 멀티라벨로 여러 개 반환
#   - DB 저장/조회 편의를 위한 labels_to_str / str_to_labels 헬퍼 추가
#   - 라벨 저장 파일명이 news_classifier.pkl -> news_classifier_multi.pkl
#
# 🆕 이번 수정 (ML이 명백한 정치/행정 기사를 오분류하는 문제 보정)
#   - LEX 사전 점수가 "압도적으로 강하게" 특정 카테고리를 가리킬 때는
#     ML 모델 결과와 상관없이 그 카테고리를 강제로 포함시키는
#     _apply_strong_rule_signal() 함수를 추가.
#   - STRONG_TITLE_KEYWORDS 의 "정치" 리스트에 부처/장관 관련 단어 보강.
#   - 근본 해결은 아니며(학습 데이터 보강 + 재학습이 근본 해결),
#     재학습 전까지 오분류를 줄여주는 안전망 역할.

import os
import csv
import pickle
import time
import urllib.request
import urllib.parse
import json
import re
import pandas as pd
import sklearn
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.pipeline import Pipeline
from dotenv import load_dotenv
import email.utils

MODEL_PATH = os.path.join(os.path.dirname(__file__), "news_classifier_multi.pkl")
ERROR_LOG_PATH = os.path.join(os.path.dirname(__file__), "classifier_errors.csv")
AMBIGUOUS_LOG_PATH = os.path.join(os.path.dirname(__file__), "ambiguous_classifications.csv")

# 네이버 검색 API 제약: start는 1~1000 사이만 허용됨 (문서 기준)
NAVER_START_MAX = 1000

# 프로젝트 표준 카테고리 (순서 고정)
CATEGORIES = ["정치", "경제", "IT/과학", "라이프", "문화/트렌드", "사회/세계"]

# 멀티라벨 <-> 문자열 변환용 구분자. DB엔 "경제|IT/과학" 형태로 저장.
SEP = "|"

# 버전 불일치 안내를 1회만 출력하기 위한 플래그
_VERSION_WARNED = False


def labels_to_str(labels):
    """['경제','IT/과학'] -> '경제|IT/과학'"""
    if isinstance(labels, str):
        return labels
    return SEP.join(labels) if labels else ""


def str_to_labels(s):
    """'경제|IT/과학' -> ['경제','IT/과학']"""
    if not s:
        return []
    if isinstance(s, list):
        return s
    return [x for x in str(s).split(SEP) if x]


def log_error(function, context, exc):
    """classifier.py 전용 에러 기록 함수 (콘솔 + classifier_errors.csv)."""
    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "function": function,
        "context": context,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
    }
    file_exists = os.path.exists(ERROR_LOG_PATH)
    try:
        with open(ERROR_LOG_PATH, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except Exception as log_fail:
        print(f"⚠️ 에러 로깅 자체가 실패했습니다 (무시하고 진행): {log_fail}")

    print(f"❌ [classifier.py::{function}] {context} → {type(exc).__name__}: {exc}")


# =======================================================================
# 규칙기반 fallback 신호어 사전 (모델이 없을 때 멀티라벨로 여러 개 반환)
# =======================================================================
LEX = {
    "정치": ["대통령", "국회", "의원", "여당", "야당", "민주당", "국민의힘", "국힘", "특검",
             "보완수사권", "형사소송법", "전당대회", "당대표", "최고위", "원내대표", "외교",
             "장관", "차관", "총리", "선관위", "정부", "예산안", "북한", "국방부", "행안부",
             "법무부", "탄핵", "공천", "비서실장", "지방선거",
             # 🆕 부처/행정 관련 단어 보강 (중기부 오분류 케이스 대응)
             "중기부", "기재부", "산업부", "복지부", "고용부", "교육부", "통일부",
             "인사청문회", "청문회", "후보자", "부처", "정무위", "국정감사", "국감"],
    "경제": ["코스피", "코스닥", "증시", "주가", "주식", "환율", "금리", "한은", "유가", "ETF",
             "실적", "영업익", "매출", "분양", "부동산", "아파트", "청약", "은행", "금융",
             "대출", "보험", "증권", "상장", "인수", "합병", "관세", "수출", "물가", "파업",
             "노조", "홈플러스", "유통", "종부세", "코인", "비트코인", "채권"],
    "IT/과학": ["AI", "인공지능", "반도체", "HBM", "파운드리", "로봇", "휴머노이드", "챗봇",
                "클라우드", "위성", "우주", "로켓", "양자", "보안", "해킹", "신약", "항암",
                "임상", "바이오", "촉매", "핵융합", "올림피아드", "게임", "스마트폰",
                "갤럭시", "아이폰", "닌텐도", "넥슨", "데이터센터", "메모리", "논문", "과기정통부"],
    "라이프": ["건강", "질환", "증상", "당뇨", "혈당", "다이어트", "감량", "운동", "레시피",
               "맛집", "외식", "메뉴", "과일", "수박", "폭염", "열대야", "더위", "날씨",
               "여행", "관광", "휴가", "피서", "해수욕장", "호텔", "리조트", "운세", "뷰티",
               "화장품", "패션", "식중독", "수면", "간식", "보양식", "효능"],
    "문화/트렌드": ["콘서트", "공연", "뮤지컬", "연극", "발레", "전시", "미술관", "앨범",
                    "싱글", "컴백", "뮤비", "OST", "음원", "차트", "아이돌", "걸그룹", "K팝",
                    "BTS", "임영웅", "트로트", "가수", "배우", "드라마", "영화", "시청률",
                    "예능", "축제", "페스티벌", "콩쿠르", "작가", "문학", "웹툰", "e스포츠",
                    "MSI", "LCK", "롤", "골프", "월드컵", "축구", "야구", "홈런", "별세"],
    "사회/세계": ["화재", "사고", "사망", "숨진", "숨졌", "실종", "수색", "붕괴", "침수",
                  "정전", "폭우", "호우", "지진", "구속", "체포", "송치", "기소", "검찰",
                  "경찰", "법원", "판결", "재판", "사기", "절도", "성폭력", "학폭", "범죄",
                  "마약", "음주운전", "이란", "트럼프", "호르무즈", "미사일", "전쟁", "제재",
                  "온열질환", "열사병", "태풍", "구청", "군수", "도의회", "지자체"],
}

# 제목 가중치를 본문보다 높게
TITLE_WEIGHT = 3
CONTENT_WEIGHT = 1

# -----------------------------------------------------------------------------
# [키워드 보장 규칙]
# 학습 데이터가 적은 주제(예: '패션'은 전체 863건 중 8건뿐)는 ML이 못 배운다.
# 제목에 아래 단어가 있으면 해당 카테고리를 '무조건' 포함시켜 보정한다.
# ⚠️ 여기엔 그 단어가 나오면 카테고리가 거의 확실한 것만 넣을 것.
#    (애매한 단어를 넣으면 오히려 정확도가 떨어짐)
# -----------------------------------------------------------------------------
STRONG_TITLE_KEYWORDS = {
    "라이프": ["패션", "뷰티", "화장품", "다이어트", "레시피", "맛집", "운세",
               "효능", "혈당", "건강기능"],
    "정치": ["대통령", "국회", "여당", "야당", "장관", "국무회의", "국민의힘", "민주당",
             # 🆕 부처/행정 관련 단어 보강 (중기부 오분류 케이스 대응)
             "중기부", "기재부", "산업부", "복지부", "고용부", "교육부", "통일부",
             "인사청문회", "청문회", "차관", "총리"],
    "경제": ["코스피", "코스닥", "환율", "금리", "주가", "청약", "분양가"],
    "IT/과학": ["인공지능", "반도체", "스마트폰", "갤럭시", "아이폰"],
    "문화/트렌드": ["콘서트", "뮤지컬", "드라마", "앨범", "컴백", "영화제"],
    "사회/세계": ["화재", "음주운전", "온열질환", "구속영장"],
}


def _apply_strong_keywords(labels, title):
    """제목에 확실한 키워드가 있으면 해당 라벨을 보장(추가)한다."""
    t = str(title)
    out = list(labels)
    for cat, kws in STRONG_TITLE_KEYWORDS.items():
        if cat not in out and any(k in t for k in kws):
            out.append(cat)
    return out


# -----------------------------------------------------------------------------
# 🆕 [ML 오분류 보정] LEX 사전 점수가 "압도적"일 때 ML 결과에 강제 반영
#
#   문제 상황: ML 모델은 있는데, 학습 데이터가 부족한 주제(예: 정치-행정)에서
#             ML이 명백히 틀린 카테고리를 내놓는 경우가 있음.
#             (예: "중기부 장관 인사청문회" 기사를 '문화/트렌드'로 오분류)
#
#   해결 아이디어: LEX 사전 규칙기반 점수를 함께 계산해서,
#             특정 카테고리 점수가 "명백한 수준(threshold)"을 넘으면
#             ML이 그 카테고리를 놓쳤더라도 강제로 추가한다.
#             (ML이 낸 다른 라벨을 지우지는 않음 - 안전하게 추가만)
# -----------------------------------------------------------------------------
STRONG_RULE_SCORE_THRESHOLD = 6  # 이 점수 이상이면 "확신"으로 간주 (제목 가중치 3점이므로 키워드 2개 매칭 = 6점)


def _apply_strong_rule_signal(ml_labels, title, content=""):
    """LEX 사전 점수가 압도적인 카테고리가 있으면 ML 결과에 강제로 추가."""
    t, s = str(title), str(content)
    scores = {c: 0 for c in CATEGORIES}
    for c, kws in LEX.items():
        for kw in kws:
            scores[c] += t.count(kw) * TITLE_WEIGHT + s.count(kw) * CONTENT_WEIGHT

    out = list(ml_labels)
    for cat, score in scores.items():
        if cat not in out and score >= STRONG_RULE_SCORE_THRESHOLD:
            out.append(cat)
            print(f"⚡ [규칙기반 보정] LEX 점수 {score}점으로 '{cat}' 강제 추가 (ML 원래 결과: {ml_labels})")
    return out


def predict_category_rule_based(title, content=""):
    """모델이 없을 때 쓰는 규칙기반 멀티라벨 분류 (최소 1개 보장, 최대 3개)."""
    t, s = str(title), str(content)
    scores = {c: 0 for c in CATEGORIES}
    for c, kws in LEX.items():
        for kw in kws:
            scores[c] += t.count(kw) * TITLE_WEIGHT + s.count(kw) * CONTENT_WEIGHT

    top = max(scores.values())
    if top == 0:
        return ["사회/세계"]  # 신호어가 전혀 없을 때 기본값

    chosen = [c for c in CATEGORIES if scores[c] >= max(2, 0.45 * top)]
    chosen = sorted(chosen, key=lambda c: -scores[c])[:3]
    return chosen or [max(scores, key=scores.get)]


def is_published_today(pub_date_str):
    """네이버 API의 pubDate를 분석해 '오늘' 기사인지 판별"""
    if not pub_date_str:
        return False
    try:
        parsed_tuple = email.utils.parsedate_tz(pub_date_str)
        if parsed_tuple:
            pub_date = datetime(*parsed_tuple[:6]).date()
            return pub_date == datetime.now().date()
    except Exception:
        pass
    return False


# =======================================================================
# 예측: 항상 '리스트'를 반환 (멀티라벨)
# =======================================================================
def predict_category(title, content=""):
    """
    뉴스 제목/본문 기반 카테고리 예측.
    ⚠️ 반환값이 문자열 하나가 아니라 '리스트'입니다.  예: ['경제', 'IT/과학']
    """
    text = f"{title} {content}"

    if os.path.exists(MODEL_PATH):
        try:
            with open(MODEL_PATH, "rb") as f:
                bundle = pickle.load(f)
            pipeline, mlb = bundle["pipeline"], bundle["mlb"]

            # 학습 때와 지금의 scikit-learn 버전이 다르면 1회만 안내
            global _VERSION_WARNED
            trained_v = bundle.get("sklearn_version")
            if trained_v and trained_v != sklearn.__version__ and not _VERSION_WARNED:
                _VERSION_WARNED = True
                print(f"⚠️ 모델은 scikit-learn {trained_v} 로 학습됐는데 현재는 {sklearn.__version__} 입니다.")
                print("   경고를 없애려면 이 환경에서 'python train_model.py' 로 다시 학습하세요.")

            Y_pred = pipeline.predict([text])
            labels = list(mlb.inverse_transform(Y_pred)[0])

            # 아무 것도 안 잡히면(전부 0) 점수 최고 1개라도 강제 선택
            if not labels:
                scores = pipeline.decision_function([text])[0]
                labels = [list(mlb.classes_)[scores.argmax()]]

            # 🆕 1) LEX 사전이 압도적으로 확신하는 카테고리가 있으면 강제 추가
            labels = _apply_strong_rule_signal(labels, title, content)

            # 2) 학습 데이터가 적은 주제 보정 (예: 패션 -> 라이프)
            return _apply_strong_keywords(labels, title)
        except Exception as e:
            log_error("predict_category", f"title={str(title)[:30]}", e)
            print("⚠️ ML 모델 예측 실패로 규칙 기반으로 전환합니다.")

    return _apply_strong_keywords(predict_category_rule_based(title, content), title)


# =======================================================================
# 학습: MultiLabelBinarizer + OneVsRest(LinearSVC)
# =======================================================================
def train_and_save_model(train_texts, train_label_lists):
    """
    train_texts       : ["제목 본문", ...]
    train_label_lists : [["경제","IT/과학"], ["문화/트렌드"], ...]   # 행마다 라벨 '리스트'
    """
    mlb = MultiLabelBinarizer(classes=CATEGORIES)
    Y = mlb.fit_transform(train_label_lists)

    pipeline = Pipeline([
        # 한국어는 조사/어미 때문에 단어 단위가 불리 -> 문자 n-gram(2~4) 사용
        # (filter.py, cluster.py 와 동일한 접근)
        ("tfidf", TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=2)),
        # class_weight="balanced": 소수/모호 클래스 재현율 보강
        ("clf", OneVsRestClassifier(LinearSVC(C=0.5, class_weight="balanced"))),
    ])
    pipeline.fit(train_texts, Y)

    # 학습에 쓴 scikit-learn 버전을 함께 저장 -> 로드 시 불일치 감지용
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"pipeline": pipeline, "mlb": mlb, "sklearn_version": sklearn.__version__}, f)
    print(f"🎯 [멀티라벨 학습 완료] {MODEL_PATH} 로 저장되었습니다! (sklearn {sklearn.__version__})")


# =======================================================================
# 📡 네이버 API 기능 (기존 로직 유지, 멀티라벨만 반영)
# =======================================================================
def clean_html(text):
    """네이버 API 텍스트 정제 후 온전한 '두 문장'만 남기는 청소 함수."""
    if not text:
        return ""

    noise_sentences = [
        r"AI 자동 인식으로 제공되는 검색 링크를 통해 본문을 듣길 종료하였다\.",
        r"AI 자동 인식으로 제공되는 검색 링크가 있습니다\.",
        r"언론사 페이지\(아웃링크\)로 이동해 볼 수 있는 기사의 섹션 정보는 해당 언론사의 분류를 따르며 선정된다\.",
        r"언론사 페이지\(아웃링크\)로 이동해 볼 수 있습니다\.",
        r"개별 기사의 섹션 정보는 해당 언론사의 분류를 따릅니다\.",
        r"오분류 제보하기에 대한 정보는 미제공될 수 있으며, 동일한 명칭이 다수 존재하는 경우에는 전체 검색 결과로 연결될 수 있다\."
    ]
    for noise in noise_sentences:
        text = re.sub(noise, "", text)

    text = re.sub(r'<[^>]*>', '', text)
    text = text.replace('&quot;', '"').replace('&apos;', "'")
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = re.sub(r'\([가-힣\s]+=.*?\)', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    text = text.replace('...', ' ').replace('..', ' ')
    text = " ".join(text.split())

    sentences = re.split(r'(?<=[.!?])\s+', text)
    clean_sentences = [s.strip() for s in sentences if s.strip() and s.strip()[-1] in ['.', '!', '?']]

    if len(clean_sentences) >= 2:
        final_text = f"{clean_sentences[0]} {clean_sentences[1]}"
    elif len(clean_sentences) == 1:
        final_text = clean_sentences[0]
    else:
        final_text = text + "." if text and text[-1] not in ['.', '!', '?'] else text

    return re.sub(r"\s+", " ", final_text).strip()


def _request_naver_news(client_id, client_secret, keyword, display, start, sort="date",
                        max_retries=3, backoff_seconds=1.5):
    """네이버 뉴스 검색 API 공통 호출 함수 (재시도 + 파라미터 보정)."""
    display = max(1, min(display, 100))
    start = max(1, min(start, NAVER_START_MAX))

    encText = urllib.parse.quote(keyword)
    url = (f"https://openapi.naver.com/v1/search/news.json"
           f"?query={encText}&display={display}&start={start}&sort={sort}")

    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", client_id)
    request.add_header("X-Naver-Client-Secret", client_secret)

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            response = urllib.request.urlopen(request, timeout=10)
            if response.getcode() == 200:
                return json.loads(response.read().decode('utf-8'))
            raise RuntimeError(f"네이버 API 응답 코드 {response.getcode()}")
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                wait = backoff_seconds * attempt
                print(f"⚠️ API 호출 실패 (시도 {attempt}/{max_retries}) → {wait:.1f}초 후 재시도: {e}")
                time.sleep(wait)
            else:
                raise last_exc


def _classify_items(news_data, seen_titles):
    """
    API items를 정제 + 멀티라벨 분류 + 중복 제거.
    CSV 저장을 위해 category는 'A|B' 문자열로 직렬화해서 담는다.
    """
    rows = []
    for item in news_data.get('items', []):
        if not is_published_today(item.get('pubDate', '')):
            continue

        title = clean_html(item['title'])
        content = clean_html(item['description'])

        if title in seen_titles:
            continue
        seen_titles.add(title)

        auto_labels = predict_category(title=title, content=content)  # list
        rows.append({"text": f"{title} {content}", "category": labels_to_str(auto_labels)})
        print(f"✅ 자동 분류 완료 -> [{labels_to_str(auto_labels)}] {title[:30]}...")
    return rows


def fetch_naver_news_and_save(client_id, client_secret, search_keyword="뉴스", display_count=100):
    """네이버 API로 뉴스 검색 후 멀티라벨 자동 분류해 CSV로 저장."""
    print(f"📡 네이버 뉴스 API 연결 중... 검색어: '{search_keyword}' ({display_count}개 수집)")
    try:
        news_data = _request_naver_news(client_id, client_secret, search_keyword, display_count, start=1)
        seen_titles = set()
        dataset_rows = _classify_items(news_data, seen_titles)

        df = pd.DataFrame(dataset_rows)
        SAVE_PATH = os.path.join(os.path.dirname(__file__), "news_dataset.csv")
        df.to_csv(SAVE_PATH, index=False, encoding="utf-8-sig")

        print("\n" + "=" * 50)
        print("🎉 네이버 API 실시간 데이터로 CSV 생성 성공!")
        print(f"📍 저장 경로: {os.path.abspath(SAVE_PATH)}")
        print("=" * 50)
    except Exception as e:
        log_error("fetch_naver_news_and_save", f"keyword={search_keyword}", e)


# =======================================================================
# 🔄 배치 수집 실행부
# =======================================================================
if __name__ == "__main__":
    load_dotenv()

    CLIENT_ID = os.getenv("NAVER_CLIENT_ID") or os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET") or os.getenv("CLIENT_SECRET")

    if not CLIENT_ID or not CLIENT_SECRET:
        print("❌ 에러: .env 파일에서 네이버 API 키를 찾을 수 없습니다.")
    else:
        TOTAL_COUNT = 250
        BATCH_SIZE = 100
        target_keyword = "라이프"

        print(f"📡 '{target_keyword}' 관련 뉴스 {TOTAL_COUNT}개 수집 시작...")
        all_dataset_rows = []
        seen_titles = set()

        for start_index in range(1, TOTAL_COUNT + 1, BATCH_SIZE):
            if start_index > NAVER_START_MAX:
                print(f"⚠️ start_index({start_index})가 네이버 API 제한(최대 {NAVER_START_MAX})을 초과해 중단합니다.")
                break

            remaining = TOTAL_COUNT - len(all_dataset_rows)
            current_display = min(BATCH_SIZE, remaining) if remaining > 0 else BATCH_SIZE
            print(f"📥 검색 시작 위치: {start_index}번째부터 {current_display}개 가져오는 중...")

            try:
                news_data = _request_naver_news(
                    CLIENT_ID, CLIENT_SECRET, target_keyword,
                    display=current_display, start=start_index, sort="date"
                )
                all_dataset_rows.extend(_classify_items(news_data, seen_titles))
                if len(all_dataset_rows) >= TOTAL_COUNT:
                    all_dataset_rows = all_dataset_rows[:TOTAL_COUNT]
                    break
            except Exception as e:
                log_error("__main__ 수집 루프", f"keyword={target_keyword}, start={start_index}", e)
                break

        if all_dataset_rows:
            df = pd.DataFrame(all_dataset_rows)
            SAVE_PATH = os.path.join(os.path.dirname(__file__), "news_dataset.csv")
            try:
                df.to_csv(SAVE_PATH, index=False, encoding="utf-8-sig")
                print("\n" + "=" * 50)
                print("🎉 뉴스 수집 완료!")
                print(f"📍 저장 위치: {os.path.abspath(SAVE_PATH)}")
                print(f"📊 총 수집된 뉴스 개수: {len(df)}개 (중복 제거 후)")
                print("=" * 50)
            except Exception as e:
                log_error("__main__ CSV 저장", f"save_path={SAVE_PATH}, rows={len(df)}", e)
        else:
            print("⚠️ 수집된 뉴스가 없습니다.")