# backend/train_model.py  (멀티라벨 버전)
import os
import sys
import pandas as pd

# --- 실행 위치에 상관없이 backend/ 루트를 찾아 import 경로에 추가 -------------
def _find_backend_root(start):
    d = start
    for _ in range(6):
        if os.path.isdir(os.path.join(d, "utils")) and os.path.isdir(os.path.join(d, "database")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return start

_ROOT = _find_backend_root(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ---------------------------------------------------------------------------

# 프로젝트 루트가 backend/ 이므로 backend. 접두어 없이 utils 로 임포트
from utils.classifier import train_and_save_model, str_to_labels


def run_training():
    # 검수/중복제거까지 끝난 최종 학습 파일 (columns: title, summary, categories)
    csv_path = os.path.join(os.path.dirname(__file__), "data_final.csv")

    # 파이프라인이 만든 news_dataset.csv(columns: text, category)도 지원
    fallback_path = os.path.join(os.path.dirname(__file__), "news_dataset.csv")

    if os.path.exists(csv_path):
        path, text_col, label_col = csv_path, None, "categories"
    elif os.path.exists(fallback_path):
        path, text_col, label_col = fallback_path, "text", "category"
    else:
        print(f"❌ [에러] '{csv_path}' 또는 '{fallback_path}' 가 없습니다!")
        print("💡 data_final.csv(title,summary,categories) 를 backend/ 폴더 안에 넣어주세요.")
        return

    print(f"📊 1. 학습 데이터 불러오는 중... ({os.path.basename(path)})")
    try:
        df = pd.read_csv(path, encoding='utf-8-sig')
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding='cp949')

    # 라벨 컬럼 검증
    if label_col not in df.columns:
        print(f"❌ [에러] '{label_col}' 열이 없습니다. 열 이름을 확인해 주세요! (현재: {list(df.columns)})")
        return

    # 텍스트 컬럼 구성: data_final.csv면 title+summary, news_dataset.csv면 text
    if text_col is None:
        df = df.dropna(subset=[label_col])
        train_texts = (df["title"].fillna("") + " " + df["summary"].fillna("")).tolist()
    else:
        df = df.dropna(subset=[text_col, label_col])
        train_texts = df[text_col].tolist()

    # "경제|IT/과학" -> ['경제','IT/과학'] 로 변환 (멀티라벨 핵심)
    train_label_lists = [str_to_labels(x) for x in df[label_col].tolist()]
    # 라벨이 하나도 없는 행 제거
    keep = [i for i, labs in enumerate(train_label_lists) if labs]
    train_texts = [train_texts[i] for i in keep]
    train_label_lists = [train_label_lists[i] for i in keep]

    print(f"📈 총 {len(train_texts)}개의 학습 데이터 확보 (멀티라벨)")
    print("🤖 2. MultiLabelBinarizer + OneVsRest(LinearSVC) 학습 시작...")

    train_and_save_model(train_texts, train_label_lists)

    print("\n🎉 [완료] news_classifier_multi.pkl 저장 완료!")
    print("   이제 run_pipeline.py 를 돌리면 규칙기반이 아닌 멀티라벨 ML 분류기가 작동합니다. 🚀")


if __name__ == "__main__":
    run_training()
