# backend/migrate_multilabel.py
# -----------------------------------------------------------------------------
# 기존 news_database.db 에 예전 '단일 라벨'로 저장된 기사들을
# 지금 분류기(predict_category, 멀티라벨)로 다시 돌려 category 를 'A|B' 로 갱신한다.
#
# 안전장치
#   - 실행 전 DB 파일을 news_database.backup-YYYYMMDD_HHMMSS.db 로 백업
#   - DRY_RUN=True 면 실제 UPDATE 없이 무엇이 바뀔지 미리보기만 출력
#   - RELABEL_ALL=False 면 이미 멀티라벨('|' 포함)인 행은 건너뜀
#
# 실행: backend/ 폴더에서  python migrate_multilabel.py
# -----------------------------------------------------------------------------
import os
import sys
import shutil
import sqlite3
from datetime import datetime

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

from utils.classifier import predict_category, labels_to_str
from database.db_handler import DB_PATH

# ============================ 설정 =========================================
DRY_RUN = False        # True: 미리보기만 / False: 실제 DB 갱신
RELABEL_ALL = True    # True: 전체 재분류 / False: '|' 없는(단일라벨) 행만
SEP = "|"
# ==========================================================================


def backup_db():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(
        os.path.dirname(DB_PATH), f"news_database.backup-{stamp}.db")
    shutil.copy2(DB_PATH, backup_path)
    print(f"🗄️  DB 백업 완료 → {backup_path}")


def build_text(row):
    """title + summary_1~3 을 합쳐 분류기 입력 텍스트로."""
    parts = [row["title"] or ""]
    for k in ("summary_1", "summary_2", "summary_3"):
        if row[k]:
            parts.append(row[k])
    return " ".join(parts).strip()


def run_migration():
    if not os.path.exists(DB_PATH):
        print(f"❌ DB 파일이 없습니다: {DB_PATH}")
        return

    if not DRY_RUN:
        backup_db()

    conn = sqlite3.connect(DB_PATH, timeout=20.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, title, summary_1, summary_2, summary_3, category FROM news ORDER BY id")
    rows = cur.fetchall()

    total = len(rows)
    changed = 0
    skipped = 0
    updates = []  # (new_category, id)

    for row in rows:
        old = row["category"] or ""
        # 이미 멀티라벨이면(설정에 따라) 건너뛰기
        if not RELABEL_ALL and SEP in old:
            skipped += 1
            continue

        labels = predict_category(row["title"] or "", build_text(row))
        new = labels_to_str(labels)

        if new != old:
            changed += 1
            if changed <= 20:  # 미리보기 20개만 출력
                print(f"  #{row['id']:>4}  [{old}] → [{new}]  {(row['title'] or '')[:34]}")
            updates.append((new, row["id"]))

    print("\n" + "=" * 60)
    print(f"총 {total}행 | 변경 대상 {changed}행 | 스킵 {skipped}행")
    print("=" * 60)

    if DRY_RUN:
        print("🔎 DRY_RUN=True 이므로 실제로 반영하지 않았습니다.")
        print("   반영하려면 파일 상단의 DRY_RUN 을 False 로 바꿔 다시 실행하세요.")
    else:
        cur.executemany("UPDATE news SET category = ? WHERE id = ?", updates)
        conn.commit()
        print(f"✅ {len(updates)}행 갱신 완료 (DB 반영됨).")

    conn.close()


if __name__ == "__main__":
    run_migration()
