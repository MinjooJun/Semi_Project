import pandas as pd


def refine_dataset(file_path):
    # 1. 데이터 불러오기
    df = pd.read_csv(file_path)
    print(f"✅ 정제 전 데이터 개수: {len(df)}")

    # 2. 정치 기사로 판별할 핵심 키워드 리스트
    political_keywords = [
        "대통령", "국회", "민주당", "국민의힘", "정당", "의원",
        "선거", "공천", "탄핵", "장관", "정치권", "국정감사"
    ]

    # 3. 정제 로직:
    # '사회/세계' 카테고리인데 위 키워드가 포함된 경우 '정치'로 수정
    def fix_category(row):
        if row['category'] == '사회/세계':
            if any(k in row['text'] for k in political_keywords):
                return '정치'
        return row['category']

    # 4. 카테고리 수정 적용
    df['category'] = df.apply(fix_category, axis=1)

    # 5. 결과 저장
    output_path = "news_dataset_refined.csv"
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"🚀 정제 완료! '{output_path}' 파일이 생성되었습니다.")
    print("------------------------------------------------")
    print("수정된 데이터 분포:")
    print(df['category'].value_counts())


# 실행
refine_dataset("news_dataset.csv")
