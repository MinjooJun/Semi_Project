# backend/utils/filter.py
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def clean_title(title):
    """
    뉴스 제목의 모든 노이즈를 걷어냅니다.
    - <b>, </b> 등 HTML 태그를 '가장 먼저' 제거 (안 그러면 태그 안의 b가 글자로 남아 오염)
    - [포토], [단독], &quot; 등 말머리와 HTML 특수문자 제거
    - 주요 한자(金, 尹, 韓 등)를 한글로 강제 변환
    - 모든 공백과 문장 부호를 날려 순수 '글자 덩어리'로 압축
    """
    if not title:
        return ""

    title = re.sub(r'<[^>]+>', '', title)

    title = title.replace("&quot;", "").replace("&amp;", "").replace("…", "")
    title = title.replace("'", "").replace('"', "")
    title = title.replace("“", "").replace("”", "").replace("‘", "").replace("’", "")

    title = re.sub(r'\[.*?\]', '', title)
    title = re.sub(r'\(.*?\)', '', title)

    hanja_map = {
        "金": "김", "尹": "윤", "韓": "한", "美": "미", "中": "중",
        "日": "일", "北": "북", "獨": "독", "英": "영", "檢": "검", "李": "이"
    }
    for hanja, hangul in hanja_map.items():
        title = title.replace(hanja, hangul)

    title = re.sub(r'[^\w]', '', title)
    return title.strip()


def _max_similarity(target, candidates, ngram=(2, 4)):
    """
    target 1개 vs candidates 여러 개의 최대 코사인 유사도.
    ⚠️ 반드시 candidates 를 '통째로' 넘길 것.
       1개씩 따로 넘기면 문서가 2개뿐이라 IDF가 무의미해져 점수가 부정확해집니다.
    """
    if not target or not candidates:
        return 0.0
    try:
        vectorizer = TfidfVectorizer(analyzer='char', ngram_range=ngram)
        matrix = vectorizer.fit_transform(list(candidates) + [target])
        scores = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
        return float(np.max(scores))
    except Exception:
        return 0.0


def find_duplicate_index(new_title, existing_titles, threshold=0.55):
    """
    [중복 위치 반환형] 중복이면 '몇 번째와 겹쳤는지' 인덱스를, 아니면 -1 을 반환.
    기존 is_duplicate_news 가 True/False 만 줘서 '누구와 겹쳤는지' 알 수 없었는데,
    보도 건수(report_count)를 누적하려면 그 대상을 알아야 하므로 인덱스를 돌려줍니다.
    """
    if not existing_titles:
        return -1

    cleaned_new = clean_title(new_title)
    cleaned_existing = [clean_title(t) for t in existing_titles]

    if not cleaned_new:
        return -1

    # 1차: 정제 후 100% 일치
    if cleaned_new in cleaned_existing:
        return cleaned_existing.index(cleaned_new)

    # 2차: 유사도
    valid = [(i, t) for i, t in enumerate(cleaned_existing) if t]
    if not valid:
        return -1

    idxs, texts = zip(*valid)
    try:
        vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 4))
        matrix = vectorizer.fit_transform(list(texts) + [cleaned_new])
        scores = cosine_similarity(matrix[-1], matrix[:-1]).flatten()
        best = int(np.argmax(scores))
        if scores[best] >= threshold:
            return idxs[best]
    except Exception:
        pass
    return -1


def is_duplicate_news(new_title, existing_titles, threshold=0.55):
    """[기존 호환용] 중복이면 True. 내부적으로 find_duplicate_index 를 씁니다."""
    return find_duplicate_index(new_title, existing_titles, threshold) >= 0


def is_duplicate_summary(new_summary, existing_summaries, threshold=0.75):
    """
    [2차 방어벽: 요약문 기반 중복 검사]
    제목 표현이 완전히 달라도("손흥민 LAFC 복귀" vs "토트넘 떠난 손흥민")
    LLM 요약의 알맹이가 같으면 여기서 잡힙니다.
    제목 필터로는 원리상 못 잡는 케이스를 담당합니다.
    """
    if not new_summary or not existing_summaries:
        return False

    max_sim = _max_similarity(new_summary, existing_summaries, ngram=(2, 3))
    if max_sim >= threshold:
        print(f"🛑 [요약문 중복 {max_sim:.2f}] 동일 사건 재보도로 판정 → 차단")
        return True
    return False


def remove_batch_duplicates(news_items, threshold=0.6):
    """
    [턴 내 중복 제거 + 보도 건수 집계]

    같은 사건 기사를 대표 1건으로 합치되, 몇 곳이 보도했는지를
    item['report_count'] 에 누적합니다.

    ⚠️ 왜 세는가:
       cluster.py 의 이슈 랭킹은 '기사가 몇 건 몰렸나'로 중요도를 매깁니다.
       중복을 그냥 버리면 모든 이슈가 1건이 되어 랭킹이 무의미해집니다.
       저장은 1건만 하되 표(票)는 살려두는 게 이 함수의 핵심입니다.
    """
    unique_items = []
    seen_titles = []

    for item in news_items:
        raw_title = item.get('title', '')
        if not raw_title:
            continue

        hit = find_duplicate_index(raw_title, seen_titles, threshold=threshold)

        if hit >= 0:
            # 버리지 않고 대표 기사에 '1표' 추가
            unique_items[hit]['report_count'] = unique_items[hit].get('report_count', 1) + 1
            print(f"🔗 같은 사건으로 병합 (누적 {unique_items[hit]['report_count']}건): "
                  f"{clean_title(raw_title)[:20]}...")
            continue

        item['report_count'] = 1
        unique_items.append(item)
        seen_titles.append(raw_title)

    return unique_items