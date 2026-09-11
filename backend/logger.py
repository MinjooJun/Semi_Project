# logger.py
import logging
import os

# 1. logs 폴더가 없으면 자동 생성
if not os.path.exists('logs'):
    os.makedirs('logs')

def get_logger(name):
    # 로거 객체 생성
    logger = logging.getLogger(name)
    logger.setLevel(logging.ERROR) # 에러만 기록
    
    # 2. 파일 핸들러: logs/crawler_errors.log에 저장
    handler = logging.FileHandler('logs/crawler_errors.log', encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s - [%(name)s] - %(message)s')
    handler.setFormatter(formatter)
    
    # 중복 로그 방지
    if not logger.handlers:
        logger.addHandler(handler)
    
    return logger