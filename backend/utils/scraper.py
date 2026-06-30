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