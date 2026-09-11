# backend/debug_classify.py
#
# 특정 기사가 왜 그 카테고리로 분류됐는지 원인을 확인하는 디버그용 스크립트.
# 실행 위치: backend/ 폴더 (python debug_classify.py)

import os
import sys

# backend 루트를 못 찾을 경우를 대비한 안전장치
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from utils.classifier import (
    predict_category,
    predict_category_rule_based,
    MODEL_PATH,
    STRONG_TITLE_KEYWORDS,
)

# 👇 원인을 확인하고 싶은 실제 제목/본문을 여기 넣으세요
title = "사령탑 빈 중기부, 하반기 집행라인 '반쪽' 위기"
content = "한성숙 장관 후보자 인사청문회가 지연되면서 중소벤처기업부의 하반기 예산 집행 계획에 차질이 우려된다."

print("=" * 60)
print(f"📰 제목: {title}")
print(f"📄 본문: {content}")
print("=" * 60)

# 1. ML 모델 파일이 존재하는지 확인
print(f"\n[1] ML 모델 파일 존재 여부: {os.path.exists(MODEL_PATH)}")
print(f"    경로: {MODEL_PATH}")

# 2. 규칙기반(rule-based)만 썼을 때 결과 (LEX 사전 기반)
rule_result = predict_category_rule_based(title, content)
print(f"\n[2] 규칙기반(LEX 사전) 단독 결과 -> {rule_result}")

# 3. 실제 predict_category() 최종 결과 (ML 모델이 있으면 ML 우선, 없으면 규칙기반)
final_result = predict_category(title, content)
print(f"\n[3] 최종 predict_category() 결과 -> {final_result}")

# 4. STRONG_TITLE_KEYWORDS 에 이 제목이 걸리는 카테고리가 있는지 확인
print(f"\n[4] STRONG_TITLE_KEYWORDS 매칭 확인:")
matched_any = False
for cat, kws in STRONG_TITLE_KEYWORDS.items():
    hit = [k for k in kws if k in title]
    if hit:
        matched_any = True
        print(f"    - '{cat}' 카테고리 강제 매칭 단어: {hit}")
if not matched_any:
    print("    - 매칭되는 강제 키워드 없음 (ML/규칙기반 판단에 전적으로 의존)")

print("\n" + "=" * 60)
print("💡 결과 해석 가이드")
print("=" * 60)
print("""
- [1]에서 모델 파일이 있다면(True) -> ML 모델이 분류를 담당한 것.
  즉, 학습 데이터(data_final.csv 또는 news_dataset.csv)에
  '중기부', '장관 인선' 같은 정치 기사가 충분히 없어서
  모델이 잘못 배웠을 가능성이 큽니다.

- [1]에서 모델 파일이 없다면(False) -> [2] 규칙기반 결과가 곧 최종 결과.
  LEX 사전에 "중기부", "장관" 같은 정치 관련 단어가
  충분히 등록되어 있지 않아서 생긴 문제입니다.

- [4]에서 매칭되는 강제 키워드가 없다면 -> STRONG_TITLE_KEYWORDS의
  '정치' 리스트에 "중기부", "장관" 같은 단어를 추가하면
  이런 케이스를 확실하게 잡아줄 수 있습니다.
""")