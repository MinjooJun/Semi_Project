# data_collector.py
import pandas as pd
from utils.scraper import get_news_by_category, extract_article_text

categories = {"100": "정치", "101": "경제", "102": "사회", "105": "IT/과학"}
all_data = []

for code, name in categories.items():
    print(f"수집 중: {name}...")
    links = get_news_by_category(code, name)
    for item in links:
        content = extract_article_text(item['url'])
        if content:
            all_data.append({"text": content, "category": name})

# CSV 파일 저장
df = pd.DataFrame(all_data)
df.to_csv("news_dataset.csv", index=False, encoding="utf-8-sig")
print(f"✅ 수집 완료! {len(all_data)}개의 기사가 news_dataset.csv에 저장되었습니다.")
