<<<<<<< Updated upstream
=======
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re


def get_news_by_category(category_code, category_name, max_pages=3):
    all_news = []
    base_url = "https://news.naver.com/main/list.naver"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

    for page in range(1, max_pages + 1):
        try:
            params = {"mode": "LSD", "mid": "sec",
                      "sid1": category_code, "page": page}
            res = requests.get(base_url, params=params,
                               headers=headers, timeout=5)
            soup = BeautifulSoup(res.text, "html.parser")

            items = soup.select("dt > a")
            for item in items:
                link = item['href']
                title = item.text.strip()

                # 본문 수집
                try:
                    sub_res = requests.get(link, headers=headers, timeout=3)
                    sub_soup = BeautifulSoup(sub_res.text, "html.parser")
                    body = sub_soup.find('div', id='dic_area')
                    if body:
                        text = body.get_text(separator=' ', strip=True)[:200]
                        all_news.append(
                            {"title": title, "text": text, "category": category_name})
                except:
                    continue

            print(f"  {category_name} - {page}페이지 완료 ({len(all_news)}개 수집중)")
            time.sleep(2)  # 차단 방지
        except:
            continue
    return all_news


if __name__ == "__main__":
    categories = {"100": "정치", "101": "경제", "102": "사회"}
    all_data = []
    for code, name in categories.items():
        print(f"🚀 {name} 수집 시작...")
        all_data.extend(get_news_by_category(code, name))

    # 여기서 CSV 저장!
    if all_data:
        df = pd.DataFrame(all_data)
        df.to_csv("news_dataset.csv", index=False, encoding="utf-8-sig")
        print(f"🎯 완료! 총 {len(df)}개의 기사가 news_dataset.csv에 저장되었습니다.")
    else:
        print("❌ 수집된 데이터가 없습니다.")
>>>>>>> Stashed changes
