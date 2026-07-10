<<<<<<< Updated upstream
import os
import urllib.request
import json
from bs4 import BeautifulSoup
from newspaper import Article, Config
from dotenv import load_dotenv

load_dotenv()
CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def fetch_naver_news_links(keyword, display_count=10):
    encText = urllib.parse.quote(keyword)
    url = f"https://openapi.naver.com/v1/search/news.json?query={encText}&display={display_count}&sort=sim"
    
    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", CLIENT_ID)
    request.add_header("X-Naver-Client-Secret", CLIENT_SECRET)
    
    try:
        with urllib.request.urlopen(request) as response:
            if response.getcode() == 200:
                return json.loads(response.read().decode('utf-8')).get('items', [])
    except Exception as e:
        print(f"❌ 네이버 API 요청 중 오류 발생: {e}")
    return []

def extract_article_text(url):
    # 케이스 A: 네이버 뉴스 자체 플랫폼 링크인 경우 (BeautifulSoup 강제 파싱)
    if "naver.com" in url:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(req) as response:
                soup = BeautifulSoup(response.read(), 'html.parser')
                article_body = soup.select_one("article#dic_area") or soup.select_one("div#newsct_article")
                if article_body:
                    return article_body.get_text(strip=True)
        except Exception:
            pass

    # 케이스 B: 일반 언론사 자체 사이트 주소인 경우 (newspaper4k + BeautifulSoup 백업)
    config = Config()
    config.browser_user_agent = USER_AGENT
    config.fetch_images = False
    
    try:
        article = Article(url, config=config)
        article.download()
        article.parse()
        if len(article.text.strip()) > 100:
            return article.text.strip()
    except Exception:
        pass
        
    # 최종 백업 파서 (일반 언론사 태그 역추적)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req) as response:
            soup = BeautifulSoup(response.read(), 'html.parser')
            for content_tag in ['div#articleBodyContents', 'div#article_body', 'div.article_body', 'div#news_content']:
                target = soup.select_one(content_tag)
                if target:
                    return target.get_text(strip=True)
    except Exception:
        pass
        
    return ""
=======
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re


def get_news_by_category(category_code, category_name, max_pages=3):
    all_news = []
    base_url = "https://news.naver.com/main/list.naver"
    # 요청 헤더를 브라우저처럼 위장
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    for page in range(1, max_pages + 1):
        try:
            params = {"mode": "LSD", "mid": "sec",
                      "sid1": category_code, "page": page}
            res = requests.get(base_url, params=params,
                               headers=headers, timeout=5)
            soup = BeautifulSoup(res.text, "html.parser")

            # 리스트 수집
            items = soup.select("dt > a")
            for item in items:
                link = item['href']
                title = item.text.strip()

                # 본문 수집 (에러 나도 넘어가도록 설정)
                try:
                    sub_res = requests.get(link, headers=headers, timeout=3)
                    sub_soup = BeautifulSoup(sub_res.text, "html.parser")
                    body = sub_soup.find('div', id='dic_area')
                    if body:
                        text = body.get_text(separator=' ', strip=True)[
                            :200]  # 앞 200자만
                        all_news.append(
                            {"title": title, "text": text, "category": category_name})
                except:
                    continue

            print(f"  {category_name} - {page}페이지 완료")
            time.sleep(2)  # 핵심: 2초 쉬기 (차단 방지)
        except:
            continue
    return all_news


if __name__ == "__main__":
    # 수집 시작
    categories = {"100": "정치", "101": "경제", "102": "사회"}
    all_data = []
    for code, name in categories.items():
        print(f"🚀 {name} 수집 시작...")
        all_data.extend(get_news_by_category(code, name))

    if all_data:
        pd.DataFrame(all_data).to_csv("news_dataset.csv",
                                      index=False, encoding="utf-8-sig")
        print("🎯 완료!")
>>>>>>> Stashed changes
