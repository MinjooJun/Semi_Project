# scraper.py

import os
import re
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

try:
    from logger import get_logger
    logger = get_logger("Scraper")
except Exception:  # logger.py 가 없어도 파이프라인이 죽지 않게 방어
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Scraper")

load_dotenv()

CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
}

# 본문 최소 길이 (보일러플레이트 제거 '후' 기준)
MIN_BODY_LEN = 250
# 제목 단어 중 본문에 몇 %가 등장해야 '진짜 본문'으로 인정할지
MIN_TITLE_OVERLAP = 0.3

# requests 로는 본문 DOM 자체가 안 내려오는 JS 렌더링 도메인
JS_RENDERED_HOSTS = ("sports.naver.com", "entertain.naver.com", "m.sports.naver.com")

# 기사 본문이 아닌, 페이지 안내/약관 문구들
BOILERPLATE_PATTERNS = [
    r"언론사 페이지\(아웃링크\)로 이동해\s*볼 수 있습니다\.?",
    r"개별 기사의 섹션 정보는 해당 언론사의 분류를 따릅니다\.?",
    r"오분류 제보(는|하기)[^.]*\.?",
    r"AI 자동 인식으로 제공되는[^.]*\.?",
    r"기술 기반의 자동 분류 시스템[^.]*\.?",
    r"무단[ ]?전재\s*(및|and)?\s*재배포\s*금지[^.]*\.?",
    r"저작권자\s*ⓒ[^\n]*",
    r"구독(하기|해지)[^.]*\.?",
    r"기사제보\s*및\s*보도자료[^.]*\.?",
    r"[\w.-]+@[\w.-]+\.\w+",          # 기자 이메일
    r"\[.*?기자\]",
    r"사진\s*=\s*[^\n]{0,20}",
]

# 이 문구가 여러 개 보이면 '본문 추출 실패'로 간주
JUNK_SIGNALS = ["오분류 제보", "아웃링크", "자동 분류 시스템", "섹션 정보는 해당 언론사",
                "AI 자동 인식", "구독해지", "로그인이 필요합니다", "페이지를 찾을 수 없습니다"]

# 우선순위 순 본문 셀렉터
ARTICLE_SELECTORS = [
    ("article", {"id": "dic_area"}),          # 네이버 일반 뉴스 (현행)
    ("div", {"id": "newsct_article"}),        # 네이버 개편판
    ("div", {"id": "articleBodyContents"}),   # 네이버 구버전
    ("div", {"id": "articeBody"}),            # 네이버 오타 ID (실제로 존재함)
    ("div", {"class": "_article_content"}),   # 네이버 스포츠/연예
    ("div", {"id": "comp_news_article"}),
    ("div", {"itemprop": "articleBody"}),     # schema.org 표준
    ("div", {"class": "article_body"}),
    ("div", {"class": "news_end"}),
    ("article", {}),                          # 최후: 그냥 <article> 태그
]


def strip_boilerplate(text: str) -> str:
    """기사 본문에 섞인 안내문/저작권/이메일 등 노이즈 제거."""
    if not text:
        return ""
    for pat in BOILERPLATE_PATTERNS:
        text = re.sub(pat, " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _title_overlap(title: str, text: str) -> float:
    """
    제목의 단어들이 본문에 얼마나 등장하는지 비율(0.0~1.0).
    본문 추출이 실패해 엉뚱한 텍스트가 잡히면 이 값이 0에 가깝게 나온다.
    """
    if not title or not text:
        return 0.0
    tokens = [t for t in re.sub(r"[^\w\s]", " ", title).split() if len(t) >= 2]
    if not tokens:
        return 1.0  # 판단 불가 → 통과시킴
    hit = sum(1 for t in tokens if t in text)
    return hit / len(tokens)


def is_junk_body(text: str, title: str = "") -> tuple:
    """
    추출된 텍스트가 '진짜 기사 본문'인지 검증.
    반환: (버려야 하면 True, 사유 문자열)
    """
    if not text:
        return True, "본문 없음"
    if len(text) < MIN_BODY_LEN:
        return True, f"본문 {len(text)}자 (기준 {MIN_BODY_LEN}자 미만)"

    hits = [s for s in JUNK_SIGNALS if s in text]
    if len(hits) >= 2:
        return True, f"안내문 문구 감지 {hits[:2]}"

    if title:
        overlap = _title_overlap(title, text)
        if overlap < MIN_TITLE_OVERLAP:
            return True, f"제목-본문 일치도 {overlap:.0%} (기준 {MIN_TITLE_OVERLAP:.0%})"

    return False, ""


def pick_article_url(item: dict) -> str:
    """
    네이버 API item 에서 '본문을 긁을 수 있는' URL 선택.
    스포츠/연예는 JS 렌더링이라 네이버 링크론 본문이 안 나옴 → 언론사 원문으로 우회.
    """
    link = item.get("link", "") or ""
    origin = item.get("originallink", "") or ""
    if any(h in link for h in JS_RENDERED_HOSTS) and origin:
        return origin
    return link or origin


def fetch_naver_news_links(query="IT", display_count=5):
    """네이버 뉴스 API를 호출하여 뉴스 링크 리스트를 가져옵니다."""
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET,
    }
    params = {"query": query, "display": display_count, "sort": "date"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            return response.json().get("items", [])
        print(f"❌ 네이버 API 호출 실패 (상태 코드: {response.status_code})")
    except Exception as e:
        print(f"❌ API 요청 중 오류 발생: {e}")
    return []


def extract_article_text(news_url, title=""):
    """
    뉴스 링크에서 본문 텍스트를 추출한다.
    ⚠️ 실패하거나 '본문이 아닌 것 같으면' None 을 반환한다.
       (예전엔 <p> 태그를 전부 긁는 폴백 때문에 페이지 안내문이 본문으로 둔갑했음)
    """
    if not news_url:
        return None

    try:
        response = requests.get(news_url, headers=HEADERS, timeout=8)
        if response.status_code != 200:
            logger.error(f"URL: {news_url} | HTTP {response.status_code}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # 본문에 섞이면 안 되는 영역 통째로 제거
        for tag in soup(["script", "style", "iframe", "noscript", "footer", "nav", "aside"]):
            tag.decompose()

        # 1) 셀렉터 우선순위대로 시도
        for name, attrs in ARTICLE_SELECTORS:
            node = soup.find(name, attrs) if attrs else soup.find(name)
            if not node:
                continue
            body = strip_boilerplate(node.get_text(" ", strip=True))
            junk, reason = is_junk_body(body, title)
            if not junk:
                return body

        # 2) 최후 폴백: <p> 태그. 단, 30자 이상인 문단만 채택 (메뉴/캡션 배제)
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        body = strip_boilerplate(" ".join(p for p in paragraphs if len(p) >= 30))
        junk, reason = is_junk_body(body, title)
        if not junk:
            return body

        logger.error(f"본문 추출 실패 | {reason} | {news_url}")
        return None

    except Exception as e:
        logger.error(f"URL: {news_url} | 에러 내용: {e}")
        return None


def get_news_image(news_url):
    """og:image 메타 태그 기반 대표 썸네일 추출 (네이버 외 언론사도 지원)."""
    if not news_url:
        return None
    try:
        response = requests.get(news_url, headers=HEADERS, timeout=5)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            img_url = og_image["content"]
            if any(bad in img_url for bad in ("naver_logo", "default", "blank.gif")):
                return None
            return img_url

        img_tag = soup.select_one("img#img1")
        if img_tag:
            return img_tag.get("data-src") or img_tag.get("src")
    except Exception as e:
        print(f"⚠️ 이미지 추출 오류 (무시됨): {e}")
    return None

def fetch_article(news_url, title=""):
    """
    본문과 대표 이미지를 '한 번의 HTTP 요청'으로 함께 추출.
    ⚠️ extract_article_text + get_news_image 를 따로 부르면 같은 페이지를 2번 받습니다.
    반환: (본문 or None, 이미지 URL or None)
    """
    if not news_url:
        return None, None
    try:
        response = requests.get(news_url, headers=HEADERS, timeout=8)
        if response.status_code != 200:
            logger.error(f"URL: {news_url} | HTTP {response.status_code}")
            return None, None

        soup = BeautifulSoup(response.text, "html.parser")

        # 이미지는 본문 태그를 지우기 '전에' 뽑아야 함 (og:image 는 <head> 에 있음)
        image_url = None
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            img = og["content"]
            if not any(bad in img for bad in ("naver_logo", "default", "blank.gif")):
                image_url = img

        for tag in soup(["script", "style", "iframe", "noscript", "footer", "nav", "aside"]):
            tag.decompose()

        for name, attrs in ARTICLE_SELECTORS:
            node = soup.find(name, attrs) if attrs else soup.find(name)
            if not node:
                continue
            body = strip_boilerplate(node.get_text(" ", strip=True))
            junk, reason = is_junk_body(body, title)
            if not junk:
                return body, image_url

        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        body = strip_boilerplate(" ".join(p for p in paragraphs if len(p) >= 30))
        junk, reason = is_junk_body(body, title)
        if not junk:
            return body, image_url

        logger.error(f"본문 추출 실패 | {reason} | {news_url}")
        return None, image_url

    except Exception as e:
        logger.error(f"URL: {news_url} | 에러 내용: {e}")
        return None, None