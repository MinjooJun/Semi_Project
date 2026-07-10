# backend/train_model.py
import os
import pandas as pd
from classifier import train_and_save_model


def run_training():
    # 1. 동생이 가져온 CSV 파일 경로 설정 (동생이 준 파일을 backend/ 폴더 안에 넣어두세요!)
    csv_path = os.path.join(os.path.dirname(__file__), "news_dataset.csv")

    if not os.path.exists(csv_path):
        print(f"❌ [에러] '{csv_path}' 위치에 동생이 만든 CSV 파일이 없습니다!")
        print("💡 동생이 준 'news_train_data.csv' 파일을 backend/ 폴더 바로 안에 복사해 주세요.")
        return

    print("📊 1. 동생이 수집한 머신러닝 데이터셋 불러오는 중...")
    try:
        # 데이터 읽기 (인코딩 에러 방지를 위해 utf-8-sig 또는 cp949 적용)
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding='cp949')

    # 데이터 검증
    if 'text' not in df.columns or 'category' not in df.columns:
        print("❌ [에러] CSV 파일의 열 이름이 'text'와 'category'가 아닙니다. 확인해 주세요!")
        return

    # 결측치(빈 칸) 제거 및 텍스트 데이터 추출
    df = df.dropna(subset=['text', 'category'])
    train_texts = df['text'].tolist()
    train_labels = df['category'].tolist()

    print(f"📈 총 {len(train_texts)}개의 정답 학습 데이터가 확보되었습니다.")
    print("🤖 2. Scikit-learn LinearSVC(SVM) 알고리즘 학습 시작...")

    # 2. 우리가 classifier.py에 만들어 두었던 학습 함수 가동!
    train_and_save_model(train_texts, train_labels)

    print("\n🎉 [최종 완료] 이제 파이프라인(run_pipeline.py)을 돌리면 임시 규칙이 아닌,")
    print("   방금 학습된 진짜 AI 머신러닝 분류기 모델이 카테고리를 실시간으로 자동 추론합니다! 🚀")


if __name__ == "__main__":
    run_training()
