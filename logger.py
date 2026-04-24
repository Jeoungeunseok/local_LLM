import logging
import os
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = os.getenv("LOG_DIR", "/app/logs")
LOG_FILE = os.path.join(LOG_DIR, "uvicorn.log")

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)

    # 날짜별 회전 핸들러 (자정마다 회전, 7일 보관)
    file_handler = TimedRotatingFileHandler(
        filename=LOG_FILE,
        when="midnight",         # 자정마다 새 파일로 회전
        interval=1,              # 1일 단위
        backupCount=7,           # 최대 7개 보관 (일주일치)
        encoding="utf-8",
        utc=False,
    )
    # 백업 파일명: uvicorn.log.2026-04-24.log 형식
    file_handler.suffix = "%Y-%m-%d.log"
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    file_handler.setLevel(logging.INFO)

    # 콘솔(터미널)에도 동시 출력
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    console_handler.setLevel(logging.INFO)

    # uvicorn 관련 로거 3종 모두 가로채서 파일에 기록
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        # 기존 핸들러 제거 후 새 핸들러 추가 (중복 방지)
        logger.handlers.clear()
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.propagate = False

    # FastAPI/애플리케이션 전용 로거도 동일 설정 적용
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.handlers.clear()
    app_logger.addHandler(file_handler)
    app_logger.addHandler(console_handler)
    app_logger.propagate = False

    logging.getLogger("app").info(f"로깅 시스템 시작 | 저장 경로: {LOG_FILE} | 보관 기간: 7일")
