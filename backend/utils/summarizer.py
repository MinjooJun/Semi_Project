# summarizer.py
import json
import requests
import nltk
import re

# 최초 1회 자연어 처리 토크나이저 다운로드 보장
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt', quiet=True)
    nltk.download('punkt_tab', quiet=True)

# 로컬 Ollama 기본 API 주소 설정
OLLAMA_URL = "http://localhost:11434/api/generate"


def summarize_news_with_ollama(article_text, title=None, model_name="llama3"):
    """
    [일반 뉴스 3줄 요약 엔진]
    크롤링해 온 원문 본문을 인풋으로 받아, 핵심 내용 딱 3줄을 
    리액트 화면 규격에 맞는 정제된 JSON 배열 포맷으로 리턴합니다.

    🆕 title 파라미터 추가:
      기사 제목을 함께 넘기면 프롬프트에 [기사 제목] 섹션으로 포함시켜
      LLM이 핵심을 더 정확히 잡도록 돕습니다. title이 없어도(None) 기존과
      동일하게 본문만으로 요약하므로 하위 호환됩니다.
    """
    title_context = f"\n    [기사 제목]\n    {title}\n" if title else ""

    prompt = f"""
    [엄격 규칙] 당신은 한국어 뉴스 요약 전문가입니다.
    다음 제공되는 뉴스 제목과 본문을 분석하여 가장 중요한 핵심 내용을 딱 3줄의 순수 한국어로만 요약하세요.
    반드시 한국어(Korean)로만 답변하고, 아래 규격의 JSON 포맷으로만 출력하세요. 다른 인사말이나 텍스트는 절대 포함하지 마십시오.
    각 문장은 반드시 완결된 서술형 문장으로 작성하고, 끝에 마침표(.)를 반드시 붙이세요.
{title_context}
    뉴스 본문:
    {article_text}

    출력 포맷:
    {{
        "summary": [
            "1번째 핵심 문장 요약 (명확하고 정제된 문체로)",
            "2번째 핵심 문장 요약",
            "3번째 핵심 문장 요약"
        ]
    }}
    """
    
    data = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1}
    }
    
    try:
            response = requests.post(OLLAMA_URL, json=data, timeout=60)
            result_text = response.json().get("response", "").strip()
            
            # 1. LLM 답변에서 JSON 부분만 정규식으로 추출 (마법의 한 줄)
            # 답변 전체에서 [ ]로 둘러싸인 배열 부분만 찾아냅니다.
            json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
            if json_match:
                clean_json = json_match.group()
                return json.loads(clean_json)
            else:
                # 2. JSON 구조가 전혀 안 보이면 LLM이 텍스트로만 뱉은 것 -> 강제 3줄 분할
                print("⚠️ JSON 파싱 실패, 텍스트를 줄바꿈 기준으로 강제 분할합니다.")
                return [line.strip() for line in result_text.split('\n') if line.strip()][:3]
                
    except Exception as e:
        print(f"❌ 요약 처리 중 오류 발생: {e}")
        return ["요약 생성 중 일시적인 오류가 발생했습니다."]


def _ensure_period(sentence: str) -> str:
    """문장 끝에 마침표가 없으면 붙여주는 안전장치"""
    s = sentence.strip()
    if s and s[-1] not in ".!?":
        s += "."
    return s


MAX_SUMMARY_LEN = 130

def _trim_to_limit(text: str, limit: int = MAX_SUMMARY_LEN) -> str:
    """
    LLM이 글자 수를 어겼을 때 문장 경계 기준으로 안전하게 절단.

    🆕 버그 수정 (130자를 넘겨서 테스트가 실패하던 문제):
      1) 기존엔 len(s) <= limit 일 때 마침표를 붙이는 _ensure_period()를
         호출했는데, 원문이 이미 limit 글자에 딱 맞고 마침표가 없으면
         마침표를 붙이는 순간 limit+1자가 되어 초과했습니다.
         → 마침표를 붙인 뒤에도 다시 한번 길이를 확인하도록 수정.
      2) rfind(m, 0, limit + 1) 는 인덱스 0~limit(=limit+1번째 글자)까지도
         검사 대상에 포함시켜서, 자칫 limit+1번째 글자에 마침표가 있어도
         cut 위치로 잡혀 s[:cut+1] 이 limit+1자가 될 수 있었습니다.
         → 끝 경계를 limit + 1 이 아니라 limit 으로 수정.
      3) 마지막에 어떤 경로로 나왔든 절대 limit자를 넘기지 않도록
         최종 하드컷(s[:limit])을 한 번 더 강제 적용.
    """
    s = re.sub(r"\s+", " ", (text or "")).strip()
    if not s:
        return ""

    if len(s) <= limit:
        result = _ensure_period(s)
        # 마침표를 붙이는 과정에서 limit을 넘겼다면 마침표 없이라도 자른다
        if len(result) > limit:
            result = result[:limit]
        return result

    # limit 이내에서의 마지막 문장 끝(. ! ?) 찾기
    # 🆕 [수정] 끝 경계를 limit+1 -> limit 으로: limit번째 인덱스(=limit+1번째 글자)에
    #    마침표가 있어도 절단 결과가 limit자를 넘지 않도록 방지.
    cut = max(s.rfind(m, 0, limit) for m in (".", "!", "?"))
    if cut >= limit * 0.5:          # 너무 짧게 잘리는 경우 방지
        result = s[:cut + 1].strip()
    else:
        # 문장 경계가 없으면 어절 단위로 자르고 말줄임
        words = s[:limit - 1].split(" ")
        if len(words) > 1:
            words.pop()
        result = " ".join(words).rstrip(",·") + "…"

    # 🆕 [최종 방어선] 위 로직을 다 거쳐도 혹시 limit을 넘기면 강제로 자른다.
    #    (예: 어절 단위 분기에서 "…"이 붙으며 limit을 살짝 넘기는 경우 등)
    if len(result) > limit:
        result = result[:limit]

    return result


def summarize_cluster_brief(cluster_articles, representative_title=None, model_name="llama3"):
    """
    [데일리 이슈 초압축 요약 엔진]
    같은 이슈로 묶인 기사들의 3줄 요약을 병합해, 카드 UI용 130자 이내 핵심 요약 1건을 생성합니다.
    반환: {"summary": str, "keyword": str}
    """
    texts = []
    for news in cluster_articles[:3]:
        parts = [news.get(f'summary_{i}', '') for i in (1, 2, 3)]
        body = "\n".join(f"- {p}" for p in parts if p and p.strip())
        if body:
            texts.append(f"[기사 제목: {news.get('title', '무제')}]\n{body}")

    combined_text = "\n\n".join(texts)
    if not combined_text.strip():
        return {"summary": _trim_to_limit(representative_title or "요약할 내용이 없습니다."), "keyword": ""}

    headline_context = f"[대표 헤드라인]\n{representative_title}\n" if representative_title else ""

    prompt = f"""
[역할] 당신은 한국어 뉴스 데스크의 데일리 브리핑 에디터입니다.

[입력 설명] 아래 "기사 데이터셋"은 같은 이슈를 다룬 여러 언론사 기사의 3줄 요약을 모아둔 것입니다.
원문 전체가 아니라 이미 요약된 조각들이므로, 조각에 없는 사실은 절대 채워 넣지 마세요.
{headline_context}
[작업] 어제 하루 이 이슈를 놓친 독자가 이 한 덩어리만 읽고 상황을 파악할 수 있도록 요약하세요.

[판단 기준 — 무엇을 남기고 무엇을 버릴지]
남길 것 (우선순위 순):
  1. 누가(주체) — 인물/기업/기관 이름
  2. 무엇을 했나(사건의 결정적 행위나 결과) — 가장 중요합니다
  3. 규모나 수치 — 금액, 인원, 퍼센트처럼 사건의 크기를 보여주는 숫자
  4. 그래서 어떻게 됐나(직접적 파장이나 다음 단계)
버릴 것:
  - 배경 설명, 역사적 맥락, 일반론
  - 언제/어디 — 어제 뉴스이므로 시점은 자명합니다. 날짜가 사건의 핵심일 때만 넣으세요.
  - 관계자 발언 인용, 전문가 논평
  - "~할 전망이다", "~에 관심이 쏠린다" 같은 기자의 추측성 마무리

[절대 규칙]
1. 전체 1~2문장, 공백 포함 130자 이내. 이 제한은 절대적입니다. 130자를 넘기면 실패입니다.
2. 문어체 평서문("~했다", "~됐다")으로 끝내세요. 명사형 종결("~함", "~발표") 금지.
3. 관형절을 겹쳐 쓰지 마세요. "~한 가운데 ~라고 밝힌 것으로 알려진" 같은 문장은 금지입니다.
   짧은 문장 2개가 긴 문장 1개보다 낫습니다.
4. 데이터에 없는 사실, 숫자, 이름을 지어내지 마세요.
5. 여러 기사가 서로 다른 내용을 말하면, 가장 많은 기사가 공통으로 다루는 사실만 쓰세요.
6. 고유명사를 제외하고 한국어로만 답변하세요.
7. 인사말, 설명, 마크다운 기호 없이 지정된 JSON만 출력하세요.

[기사 데이터셋]
{combined_text}

[출력 JSON 형식]
{{
    "summary": "130자 이내 핵심 요약",
    "keyword": "이 이슈를 대표하는 단어 하나 (2~6자)"
}}
"""

    data = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": 300}
    }

    try:
        response = requests.post(OLLAMA_URL, json=data, timeout=180)
        if response.status_code == 200:
            parsed = json.loads(response.json().get("response", "{}"))
            summary = _trim_to_limit(str(parsed.get("summary", "")))
            if summary:
                return {"summary": summary, "keyword": str(parsed.get("keyword", ""))[:10]}
    except Exception as e:
        print(f"❌ 데일리 이슈 요약 실패: {e}")

    # 폴백: 대표 기사의 첫 문장이라도 살려서 화면에 빈칸이 뜨지 않게 방어
    fallback = cluster_articles[0].get('summary_1', '') if cluster_articles else ''
    return {"summary": _trim_to_limit(fallback or (representative_title or "요약 생성에 실패했습니다.")),
            "keyword": ""}