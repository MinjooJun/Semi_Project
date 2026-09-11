# C:\Users\enjoy\Desktop\semi\backend\recovery_service.py
import time
import os
import requests
import json

# 로그 파일 절대 경로로 고정
LOG_FILE_PATH = r"C:\Users\enjoy\Desktop\semi\backend\logs\crawler_errors.log"
OLLAMA_URL = "http://localhost:11434/api/generate"

# 💥 [중요]여기에 디스코드 채널 웹훅 URL 주소를 넣으세요!
DISCORD_WEBHOOK_URL = "https://discordapp.com/api/webhooks/1522425036693176330/LgccGbyrZaBkLgXr8Ug0lpfLQAaWemmXIhgt51_UXYcpChmdoHYEY4N3DStAZer2DhWI"

def analyze_error_with_ai(error_line):
    """
    지능형 관제 AI 비서: 수집기 로그를 분석하여 한국어 리포트를 생성
    """
    # Llama 3 경량 모델의 한글 고정을 위해 시스템 명령(System Prompt) 구조를 더 명확하게 강화
    prompt = f"""
    당신은 실시간 수집 시스템을 모니터링하는 전문 관제 AI 비서입니다.
    반드시 반드시 모든 답변을 한국어(Korean)로만 작성해야 합니다. 영어를 사용하지 마세요.

    아래의 크롤러 에러 로그를 분석하여 개발팀이 즉시 대처할 수 있도록 '장애 분석 리포트'를 가이드에 맞춰 작성해 주세요.

    [에러 로그]
    {error_line}

    [출력 포맷]
    🚨 **[뉴스 파이프라인 장애 알림]**
    - 🕒 **발생 시간**: 로그에 기록된 시간 적기
    - 🔍 **장애 발생 위치**: 문제가 터진 모듈 또는 URL 기재
    - ⚠️ **원인 분석 (AI)**: 사이트 구조 변경(DOM 개편) 가능성, 네트워크 끊김, 파싱 에러 중 판단하여 쉽게 설명
    - 🛠 **추천 조치**: 개발자가 지금 바로 확인해야 할 사항 제시
    """
    
    payload = {
        "model": "llama3",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2  # 일관된 한국어 출력을 위해 창의성을 낮춤
        }
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return result.get("response", "AI 요약본을 추출할 수 없습니다.")
        else:
            return f"❌ Ollama 통신 실패 (Status Code: {response.status_code})"
    except Exception as e:
        return f"❌ AI 비서 분석 중 내부 연산 에러 발생: {str(e)}"

def send_to_developer_messenger(report_text):
    """
    실제 디스코드 채널로 AI 리포트를 발송하는 함수 (빈 메시지 오류 완벽 방어)
    """
    print("\n" + "="*60)
    print("📡 [관제탑] 디스코드 채널로 AI 장애 리포트를 발송합니다.")
    print("="*60)
    print(report_text)
    print("="*60 + "\n")
    
    # 1. 혹시 모를 양끝 공백이나 이상한 개행문자 날려주기
    clean_report = str(report_text).strip()
    
    # 2. 만약 LLM 응답이 완전히 비어있거나 이상하면 최소한의 방어 텍스트 주입
    if not clean_report:
        clean_report = "⚠️ AI 비서 요약 결과가 비어있습니다. 에러 로그 파일을 직접 확인하세요."
        
    # 3. 디스코드 글자수 제한(2000자) 방어 처리
    if len(clean_report) > 1900:
        clean_report = clean_report[:1900] + "\n\n...(이하 글자수 제한으로 생략)..."

    payload = {
        "content": clean_report  # 정제된 텍스트 주입
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    if "여기에" not in DISCORD_WEBHOOK_URL:
        try:
            # 💥 data=json.dumps() 대신 requests의 내장 json 옵션을 쓰면 인코딩 문제가 원천 차단됩니다.
            res = requests.post(DISCORD_WEBHOOK_URL, json=payload, headers=headers, timeout=10)
            
            if res.status_code in [200, 204]:
                print("✅ [디스코드] 알림 전송 성공!")
            else:
                print(f"❌ [디스코드] 알림 전송 실패 (상태 코드: {res.status_code})")
                print(f"💬 디스코드 응답 내용: {res.text}")  # 에러 메시지 역추적용
        except Exception as e:
            print(f"❌ [디스코드] 통신 에러: {str(e)}")

def start_monitoring():
    print("🚀 [Self-Healing] 실시간 장애 모니터링 관제 시스템 가동 시작...")
    print(f"📂 감시 대상 경로: {LOG_FILE_PATH}")
    
    # 실시간 감지를 위해 파일 끝(2)으로 포인터 이동
    last_position = 0
    if os.path.exists(LOG_FILE_PATH):
        with open(LOG_FILE_PATH, 'r', encoding='utf-8') as f:
            f.seek(0, 2)
            last_position = f.tell()
            
    while True:
        if os.path.exists(LOG_FILE_PATH):
            with open(LOG_FILE_PATH, 'r', encoding='utf-8') as f:
                f.seek(last_position)
                new_lines = f.readlines()
                last_position = f.tell()
                
                for line in new_lines:
                    if "ERROR" in line or "❌" in line:
                        print(f"⚠️ [징후 감지] 새 장애 로그 포착. AI 비서 분석 및 디스코드 발송 중...")
                        ai_report = analyze_error_with_ai(line.strip())
                        send_to_developer_messenger(ai_report)
                        
        time.sleep(3) # 3초 주기로 단축해서 더 빠르게 감시

if __name__ == "__main__":
    start_monitoring()