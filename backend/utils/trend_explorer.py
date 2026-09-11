import requests
import xml.etree.ElementTree as ET
from collections import Counter
from konlpy.tag import Okt  # 한국어 형태소 분석기

FALLBACK_KEYWORDS = ["정치", "경제", "IT/과학", "사회/세계", "문화/트렌드", "라이프"]


def get_dynamic_keywords(target_count=10):
    """
    구글 뉴스(한국) RSS + KoNLPy 형태소 분석으로 '핫 키워드'를 추출합니다.

    ⚠️ 예전엔 set 을 써서 등장 횟수가 사라졌습니다. set 은 원소의 유무만 알 뿐
       빈도를 기억하지 않으므로, list(set)[:10] 은 '핫한 10개'가 아니라
       해시 순서로 뽑힌 '무작위 10개'였습니다. → Counter 로 교체.
    """
    url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    }

    stop_words = {
        '단독', '종합', '속보', '특보', '포토', '기자', '뉴스', '오늘', '내일', '어제',
        '전날', '입성', '올해', '내년', '시간', '오전', '오후', '하루', '개월', '이유',
        '누구', '무엇', '어디', '관련', '진행', '예정', '준비', '시작', '종료', '최초',
        '대비', '연속', '돌파', '대신', '수행', '모두', '공개', '발표', '경우', '가능',
        '상황', '문제', '생각', '사람', '이번', '지난', '현재', '자신', '때문',
    }

    keyword_counter = Counter()

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        okt = Okt()  # 형태소 분석기 엔진 시동 (첫 호출이 느림 — JVM 기동)

        for item in root.findall(".//item"):
            title = item.find("title")
            if title is None or not title.text:
                continue

            # 구글 뉴스 RSS 제목은 "제목 - 언론사" 형태라 뒤쪽 언론사명을 잘라냄
            text = title.text.strip().rsplit(" - ", 1)[0]

            nouns = okt.nouns(text)
            valid = [w for w in nouns if len(w) >= 2 and w not in stop_words]
            keyword_counter.update(valid)   # 👈 등장 횟수를 '누적'

        if not keyword_counter:
            print("⚠️ [트렌드 탐색기] 키워드 추출 실패. 기본 키워드로 전환합니다.")
            return FALLBACK_KEYWORDS

        # 2회 이상 등장한 단어를 우선 (1회짜리는 그 기사만의 단어라 트렌드가 아님)
        hot = [w for w, c in keyword_counter.most_common() if c >= 2][:target_count]

        # 2회 이상이 부족하면 1회짜리 중 상위로 채움
        if len(hot) < target_count:
            for w, _ in keyword_counter.most_common(target_count * 2):
                if w not in hot:
                    hot.append(w)
                if len(hot) >= target_count:
                    break

        final_keywords = hot[:target_count]
        print(f"🔥 [AI 트렌드 탐색 성공] 핫 키워드: "
              f"{[(w, keyword_counter[w]) for w in final_keywords]}")
        return final_keywords

    except Exception as e:
        print(f"❌ 실시간 키워드 탐색 에러 발생: {e}")
        return FALLBACK_KEYWORDS