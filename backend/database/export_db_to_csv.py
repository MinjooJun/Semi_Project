# backend/export_db_to_csv.py
# -----------------------------------------------------------------------------
# news_database.db 에 쌓인 뉴스를 학습용 news_dataset.csv 로 뽑아내는 스크립트.
#
# train_model.py 는 news_dataset.csv 를 읽을 때
#   text_col = "text", label_col = "category"
# 를 기대하므로, 이 스크립트도 그 형식(text, category)에 맞춰 내보냅니다.
#
# 실행: backend/ 폴더에서  python export_db_to_csv.py
# -----------------------------------------------------------------------------
import os
import sys
import csv
from datetime import datetime, timedelta

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

from database.db_handler import get_connection

# ============================ 설정 ==========================================
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news_dataset.csv")

# 특정 기간만 뽑고 싶으면 아래 두 값을 "YYYY-MM-DD" 형태로 지정하세요.
# None 이면 기간 제한 없이 DB에 있는 걸 전부 뽑습니다.
START_DATE = None   # 예: "2026-06-01"
END_DATE = None     # 예: "2026-07-16"

# 라벨이 비어있는 행(카테고리 미분류)은 학습에 못 쓰므로 자동 제외됩니다.
# ==========================================================================


def build_text(row):
    """title + summary_1~3 을 합쳐 분류기 학습용 텍스트로 구성."""
    parts = [row["title"] or ""]
    for k in ("summary_1", "summary_2", "summary_3"):
        if row[k]:
            parts.append(row[k])
    return " ".join(parts).strip()


def run_export():
    conn = get_connection()
    conn.row_factory = __import__("sqlite3").Row
    cursor = conn.cursor()

    query = "SELECT title, summary_1, summary_2, summary_3, category, published_at FROM news WHERE 1=1"
    params = []

    if START_DATE:
        query += " AND published_at >= ?"
        params.append(START_DATE)
    if END_DATE:
        query += " AND published_at <= ?"
        params.append(END_DATE)

    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()

    print(f"📦 DB에서 총 {len(rows)}건을 불러왔습니다.")

    exported = 0
    skipped_empty_label = 0

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "category"])  # train_model.py 가 기대하는 컬럼명

        for row in rows:
            category = (row["category"] or "").strip()
            if not category:
                skipped_empty_label += 1
                continue

            text = build_text(row)
            if not text:
                skipped_empty_label += 1
                continue

            writer.writerow([text, category])
            exported += 1

    print("\n" + "=" * 60)
    print(f"✅ CSV 저장 완료 → {OUTPUT_PATH}")
    print(f"📊 내보낸 행: {exported}건 / 라벨(카테고리) 없어서 제외: {skipped_empty_label}건")
    print("=" * 60)
    print("💡 이제 'python train_model.py' 를 실행하면 이 데이터로 학습합니다.")


if __name__ == "__main__":
    run_export()