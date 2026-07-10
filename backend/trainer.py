import pandas as pd
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB


def run_training(csv_path="news_dataset.csv", model_save_path="model.pkl"):
    # 1. 데이터 불러오기
    df = pd.read_csv(csv_path)

    # 2. 벡터화 (텍스트를 모델이 읽을 수 있는 숫자 배열로 변환)
    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(df['text'])
    y = df['category']

    # 3. 학습 (MultinomialNB는 뉴스 분류에 매우 효율적입니다)
    model = MultinomialNB()
    model.fit(X, y)

    # 4. 모델과 벡터라이저를 파일로 저장 (분류기에서 사용)
    with open(model_save_path, "wb") as f:
        pickle.dump((vectorizer, model), f)

    print(f"🚀 학습 완료! 모델이 '{model_save_path}'에 저장되었습니다.")


if __name__ == "__main__":
    run_training()
