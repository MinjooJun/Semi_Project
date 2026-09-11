# utils/cluster.py
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import AgglomerativeClustering


def _weight(article):
    """이 기사가 갖는 '표(票)' — 몇 곳이 보도했는지."""
    try:
        return max(1, int(article.get('report_count') or 1))
    except (TypeError, ValueError):
        return 1


def _build_cluster_text(news):
    """제목 + 요약 1~3을 합쳐 군집화용 텍스트 생성 (제목만 쓸 때보다 정확도 향상)"""
    parts = [news.get('title', '') or '']
    for k in ('summary_1', 'summary_2', 'summary_3'):
        v = news.get(k)
        if v:
            parts.append(v)
    return " ".join(parts)


def _fallback_single_groups(news_list):
    """군집화가 불가능하거나 무의미할 때: 각자 홀로 서는 그룹으로 처리 (report_count 순 정렬)"""
    for idx, news in enumerate(news_list):
        news['cluster_id'] = idx
    singles = sorted(news_list, key=_weight, reverse=True)
    return [[news] for news in singles]


def cluster_news_groups(news_list, n_clusters=5, distance_threshold=0.9):
    """
    [뉴스 군집화 - 그룹 통째로 반환]
    TF-IDF + AgglomerativeClustering(거리 기반 자동 병합)으로 묶은 뒤,
    '보도량(report_count 합계)'이 큰 순서대로
    [[기사,기사,...], [기사,...], ...] 형태로 리턴합니다.

    ⚠️ 군집화 방식을 KMeans -> AgglomerativeClustering 으로 바꾼 이유:
       KMeans는 군집 개수(n_clusters)를 미리 고정해야 해서, 실제 이슈가
       n_clusters보다 적어도 억지로 쪼개다 보니 같은 사건이 두 군집으로
       갈라지는 문제가 있었습니다. distance_threshold 기반이면 유사도가
       충분히 높은 기사끼리만 자동으로 묶이고, 남는 군집 수는 가변적입니다.
       (n_clusters는 이제 "최종적으로 몇 개까지 결과로 보여줄지"의 상한선 역할)

    ⚠️ 정렬 기준이 len(members)가 아니라 report_count 합계인 이유:
       remove_batch_duplicates 가 같은 사건을 대표 1건으로 병합하므로,
       기사 '개수'만 세면 12곳이 보도한 대형 이슈도 1건으로 잡혀 랭킹이 무너집니다.
    """
    if not news_list:
        return []

    # 기사 수가 군집 수보다 적으면(수집 초기/주말처럼 기사가 적을 때) 군집화 자체가
    # 무의미하므로 각자 홀로 서는 그룹으로 처리 (원래 KMeans 버전의 동작과 동일하게 복원)
    if len(news_list) < n_clusters:
        return _fallback_single_groups(news_list)

    # 1. 제목+요약 벡터화 (제목만 쓸 때보다 같은 이슈 판별력이 올라감)
    texts = [_build_cluster_text(news) for news in news_list]

    # 🛡️ 안전장치: 제목이 전부 1글자짜리("A","B","C" 등)처럼 극단적으로 짧으면
    #    char ngram_range=(2,3) 으로는 뽑을 단어(vocabulary)가 하나도 없어서
    #    "empty vocabulary" 에러가 납니다. 이럴 때는 ngram_range=(1,2)로 낮춰서 재시도.
    try:
        vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(2, 3))
        tfidf_matrix = vectorizer.fit_transform(texts).toarray()
    except ValueError:
        try:
            vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(1, 2))
            tfidf_matrix = vectorizer.fit_transform(texts).toarray()
        except ValueError:
            # 그래도 안 되면(텍스트가 전부 빈 문자열 등) 군집화를 포기하고 단독 처리
            return _fallback_single_groups(news_list)

    # 2. 계층적 군집화: 개수를 정하지 않고 거리 기준으로 자동 병합
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric='cosine',
        linkage='average'
    )
    cluster_labels = clustering.fit_predict(tfidf_matrix)

    for idx, label in enumerate(cluster_labels):
        news_list[idx]['cluster_id'] = int(label)

    # 3. 군집별 보도량 합계 계산 후 내림차순 정렬
    groups = []
    for label in np.unique(cluster_labels):
        members = [n for n in news_list if n.get('cluster_id') == int(label)]
        if not members:
            continue
        # 군집 안에서도 많이 보도된 기사가 앞에 오도록 → members[0]이 진짜 대표가 됨
        members.sort(key=_weight, reverse=True)
        groups.append((sum(_weight(m) for m in members), members))

    groups.sort(key=lambda g: -g[0])
    return [members for _, members in groups[:n_clusters]]


def cluster_and_get_top_news(news_list, n_clusters=5):
    """
    [기존 호환용] 각 군집의 대표 기사 1개씩만 뽑아 납작한 리스트로 리턴.
    /api/news/top5 가 이 함수를 그대로 씁니다.
    """
    groups = cluster_news_groups(news_list, n_clusters=n_clusters)
    return [group[0] for group in groups if group]