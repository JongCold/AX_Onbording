import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Config:
    # Slack 설정
    SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
    SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    SLACK_USER_TOKEN = os.getenv("SLACK_USER_TOKEN")
    SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

    # 워크스페이스 주소 및 외부 노출 주소
    SLACK_PROJECT_URL = os.getenv("SLACK_PROJECT_URL", "slack-vjk8629.slack.com")
    NGROK_URL = os.getenv("NGROK_URL", "https://seducing-issue-overflow.ngrok-free.dev")
    SLACK_INVITE_URL = os.getenv("SLACK_INVITE_URL")

    # SMTP 이메일 설정
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

    # Google 설정
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
    GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

    # Ollama 설정 (사용 안함 - 응답성이 빠른 Gemini로 대체)
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma2:2b")
    OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

    # Gemini 설정 (빠른 응답성을 위한 기본 LLM)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    # 서버 설정
    PORT = int(os.getenv("PORT", 8000))
    
    # DB 및 다운로드 디렉토리 설정
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
    CHROMA_DB_DIR = os.path.join(BASE_DIR, "chroma_db")

    @classmethod
    def init_directories(cls):
        """필요한 디렉토리 생성"""
        os.makedirs(cls.DOWNLOAD_DIR, exist_ok=True)
        os.makedirs(cls.CHROMA_DB_DIR, exist_ok=True)

Config.init_directories()
