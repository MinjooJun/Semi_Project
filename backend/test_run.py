import requests
import pandas as pd
from bs4 import BeautifulSoup


def simple_test():
    print("수집 시작...")
    url = "https://news.naver.com/main/list.naver?mode=LSD&mid=sec&sid1=101"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")
    items = soup.select("dt > a")

    data = []
    for item in items[:5]:  # 딱 5개만 테스트
        data.append({"title": item.text.strip(), "link": item['href']})

    if data:
        df = pd.DataFrame(data)
        df.to_csv("test.csv", index=False, encoding="utf-8-sig")
        print("성공! test.csv 파일이 생성되었습니다.")
    else:
        print("실패: 데이터를 가져오지 못했습니다.")


if __name__ == "__main__":
    simple_test()
