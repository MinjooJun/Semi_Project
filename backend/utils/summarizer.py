# 나중에 다른 LLM으로 스위칭할 때 이 파일만 수정하면 됨

import json
import requests
import nltk

# 최초 1회 자연어 처리 모델 다운로드 보장
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt', quiet=True)
    nltk.download('punkt_tab', quiet=True)

def summarize_news_with_ollama(article_text, model_name="llama3"):
    url = "http://localhost:11434/api/generate"
    
    prompt = f"""
    [엄격 규칙] 당신은 뉴스 요약 전문가입니다. 반드시 한국어(Korean)로만 답변하고, 아래 규격의 JSON 포맷으로만 출력하세요. 다른 인사말이나 텍스트는 절대 포함하지 마십시오.

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
        "format": "json",  # 하드웨어 레벨에서 JSON 출력 강제
        "options": {"temperature": 0.1}
    }
    
    try:
        response = requests.post(url, json=data, timeout=60)
        if response.status_code == 200:
            result_json = json.loads(response.json()['response'])
            return result_json.get('summary', ["뉴스 요약 실패", "형식 오류", "내용 체크 필요"])
    except Exception as e:
        print(f"❌ Ollama 요약 연산 또는 파싱 실패: {e}")
    
    return ["뉴스 요약 실패", "오류 발생", "체크 필요"]