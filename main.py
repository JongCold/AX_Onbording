import os
import json
import asyncio
import shutil
import smtplib
from collections import deque
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Form, UploadFile, File
from fastapi.responses import JSONResponse, PlainTextResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from config import Config
from drive_service import GoogleDriveService
from rag_service import RAGService
from slack_service import SlackService
import google.generativeai as genai

def send_invite_email(to_email: str, name: str, invite_url: str) -> bool:
    """SMTP를 이용하여 신입 근로자에게 슬랙 워크스페이스 가입 초대장 메일을 발송"""
    if not Config.SMTP_USER or not Config.SMTP_PASSWORD:
        print("[WARNING] SMTP 계정 정보(SMTP_USER / SMTP_PASSWORD)가 설정되지 않아 가입 메일 발송을 건너뜁니다.")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = Config.SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = f"[{name}님] 슬랙 워크스페이스 초대장 안내"
        
        body_content = f"""
        <div style="font-family: 'Noto Sans KR', Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e1e1e1; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
            <div style="background-color: #4a154b; padding: 24px; text-align: center; color: white;">
                <h2 style="margin: 0; font-size: 22px;">Slack Workspace 초대 안내</h2>
            </div>
            <div style="padding: 32px; color: #333333; line-height: 1.6;">
                <p style="font-size: 16px; margin-top: 0;">안녕하세요, <strong>{name}님</strong>!</p>
                <p>귀하의 원활한 업무 온보딩 및 소통을 위해 전용 슬랙(Slack) 워크스페이스 가입 링크를 발송해 드립니다.</p>
                <p>아래 <strong>'워크스페이스 참여하기'</strong> 버튼을 클릭하여 슬랙에 가입 및 채널 합류를 진행해 주세요.</p>
                <div style="text-align: center; margin: 32px 0;">
                    <a href="{invite_url}" style="background-color: #10b981; color: white; padding: 14px 28px; text-decoration: none; font-weight: bold; border-radius: 6px; display: inline-block; box-shadow: 0 4px 6px rgba(16,185,129,0.2);">워크스페이스 참여하기</a>
                </div>
                <p style="color: #666666; font-size: 14px;">※ 가입 완료 즉시 담당 온보딩 프로젝트 채널에 자동으로 연동되며 챗봇 가이드 메시지가 발송됩니다.</p>
            </div>
            <div style="background-color: #f8f9fa; padding: 16px; text-align: center; font-size: 12px; color: #999999; border-top: 1px solid #eeeeee;">
                본 메일은 AX 온보딩 자동화 시스템을 통해 발송된 메일입니다.
            </div>
        </div>
        """
        msg.attach(MIMEText(body_content, 'html', 'utf-8'))
        
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
            server.sendmail(Config.SMTP_USER, to_email, msg.as_string())
            
        print(f"[SUCCESS] {to_email} 계정으로 슬랙 가입 안내 메일 전송 성공.")
        return True
    except Exception as e:
        print(f"[ERROR] 이메일 발송 중 오류 발생: {e}")
        return False

app = FastAPI(title="단기 근로자 온보딩 자동화 및 슬랙 RAG 챗봇 API")

# 🌟 [강력 수정] ngrok 프록시 레이어의 헤더 누락을 무력화하는 무조건적 CORS 헤더 강제 주입 미들웨어
@app.middleware("http")
async def force_cors_middleware(request: Request, call_next):
    # 브라우저가 보안 검증차 보낸 OPTIONS(사전 검사) 요청은 백엔드 로직을 타지 않고 즉시 빈 응답 생성
    if request.method == "OPTIONS":
        from fastapi.responses import Response
        response = Response(status_code=200)
    else:
        response = await call_next(request)
        
    # ngrok의 변형/누락 여부와 관계없이 브라우저가 요구하는 CORS 통과 도장을 무조건 강제 주입
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# static 폴더 마운트
app.mount("/static", StaticFiles(directory=os.path.join(Config.BASE_DIR, "static")), name="static")

if Config.GEMINI_API_KEY:
    genai.configure(api_key=Config.GEMINI_API_KEY)

# 각 서비스 및 파일 경로 초기화
rag_service = RAGService()
slack_service = SlackService()
PENDING_DB_PATH = os.path.join(Config.BASE_DIR, "pending_onboardings.json")

# 🌟 슬랙 중복 메시지 타임아웃 재시도 차단용 고정 정밀 큐 (FIFO 200개 제한)
PROCESSED_MSG_IDS = deque(maxlen=200)

_drive_service = None

def get_drive_service():
    global _drive_service
    if _drive_service is None:
        try:
            _drive_service = GoogleDriveService()
        except Exception as e:
            print(f"Google Drive Service Lazy Initialization failed (check credentials): {e}")
    return _drive_service

def load_pending() -> dict:
    if os.path.exists(PENDING_DB_PATH):
        try:
            with open(PENDING_DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_pending(data: dict):
    with open(PENDING_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_pending(email: str, name: str, channel_id: str):
    """신입사원 정보를 대소문자 공백을 제거한 소문자 Key 포맷으로 안전하게 펜딩 저장"""
    data = load_pending()
    normalized_email = email.strip().lower()
    data[normalized_email] = {
        "name": name,
        "channel_name": channel_id
    }
    save_pending(data)

def pop_pending(email: str) -> dict:
    """대소문자 오차 없이 소문자 정규화 매칭을 기반으로 대기자 데이터 인출"""
    data = load_pending()
    normalized_email = email.strip().lower()
    val = data.pop(normalized_email, None)
    if val:
        save_pending(data)
    return val

class OnboardRequest(BaseModel):
    name: str
    email: str
    project_name: str

def get_versioned_filename(base_dir, original_name):
    """지정한 파일명에 대해 이미 파일이 존재할 시 .ver01, .ver02 형태의 버전 접미사를 붙여 고유한 파일 경로 및 이름을 반환"""
    name_part, ext = os.path.splitext(original_name)
    version = 1
    while True:
        ver_str = f".ver{version:02d}"
        new_filename = f"{name_part}{ver_str}{ext}"
        new_path = os.path.join(base_dir, new_filename)
        if not os.path.exists(new_path):
            return new_path, new_filename
        version += 1

@app.get("/", response_class=HTMLResponse)
def read_root():
    return RedirectResponse(url="/static/index.html")

@app.post("/sync-drive")
async def sync_drive(background_tasks: BackgroundTasks):
    drive_service = get_drive_service()
    if not drive_service:
        local_pdf = os.path.join(Config.BASE_DIR, "2. 과업지시서.pdf")
        if os.path.exists(local_pdf):
            background_tasks.add_task(rag_service.index_pdf, local_pdf)
            return {"status": "success", "message": "Google Drive API가 설정되지 않아 로컬 2. 과업지시서.pdf 파일을 인덱싱합니다."}
        return {"status": "error", "message": "구글 드라이브 연동에 실패했으며, 로컬 2. 과업지시서.pdf 파일도 존재하지 않습니다."}

    def run_sync():
        files = drive_service.list_pdf_files()
        for f in files:
            file_id = f['id']
            file_name = f['name']
            print(f"Syncing Google Drive file: {file_name}")
            local_path = drive_service.download_file(file_id, file_name)
            if local_path:
                rag_service.index_pdf(local_path)

    background_tasks.add_task(run_sync)
    return {"status": "success", "message": "구글 드라이브 동기화를 백그라운드에서 진행합니다."}

@app.get("/slack/channels")
def get_slack_channels():
    """웹 UI에서 슬랙 채널 목록을 조회하기 위한 API"""
    try:
        channels = slack_service.list_public_channels()
        return {"status": "success", "channels": channels}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/onboard-web")
async def onboard_web_worker(
    name: str = Form(...),
    email: str = Form(...),
    channel_id: str = Form(...),
    task_description_pdf: UploadFile = File(None),
    onboarding_pdf: UploadFile = File(None),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    # __NEW_CHANNEL__ 선택 시 신입사원 전용 신규 슬랙 채널 동적 개설
    if channel_id == "__NEW_CHANNEL__":
        email_prefix = email.split('@')[0].lower()
        clean_prefix = "".join([c if c.isalnum() or c == '-' else '-' for c in email_prefix])
        channel_name = f"ot-proj-{clean_prefix}"
        
        created_channel = slack_service.create_channel(channel_name)
        if not created_channel:
            return JSONResponse(status_code=500, content={"status": "error", "message": f"슬랙 채널(#{channel_name}) 생성에 실패했습니다."})
        channel_id = created_channel

    # 1. 파일 업로드 로컬 저장 처리 및 .verxx 넘버링을 통한 히스토리 유지
    local_task_pdf = None
    local_task_filename = None
    local_onboard_pdf = None
    local_onboard_filename = None
    
    if task_description_pdf and task_description_pdf.filename:
        local_task_pdf, local_task_filename = get_versioned_filename(Config.BASE_DIR, "2. 과업지시서.pdf")
        with open(local_task_pdf, "wb") as buffer:
            shutil.copyfileobj(task_description_pdf.file, buffer)
            
    if onboarding_pdf and onboarding_pdf.filename:
        local_onboard_pdf, local_onboard_filename = get_versioned_filename(Config.BASE_DIR, "신입사원 온보딩.pdf")
        with open(local_onboard_pdf, "wb") as buffer:
            shutil.copyfileobj(onboarding_pdf.file, buffer)

    # 2. 백그라운드 연동 파이프라인
    async def process_pipeline():
        drive_service = get_drive_service()
        
        # 구글 드라이브 파일 업로드 (버전 이름 유지)
        if drive_service:
            if local_task_pdf:
                drive_service.upload_file(local_task_pdf)
            if local_onboard_pdf:
                drive_service.upload_file(local_onboard_pdf)
        else:
            print("Google Drive Service is uninitialized, skipping Drive uploads.")

        # RAG 실시간 임베딩 인덱싱 (새로운 고유 파일명으로 추가)
        if local_task_pdf:
            rag_service.index_pdf(local_task_pdf)
        if local_onboard_pdf:
            rag_service.index_pdf(local_onboard_pdf)

        # 대표자(관리자) 이메일 자동 초대
        ADMIN_EMAIL = "kjhkjh10114@gmail.com"
        slack_service.invite_user_by_email(channel_id, ADMIN_EMAIL, "대표자(관리자)")
            
        # 가입 완료 혹은 즉시 초대 처리
        invited = slack_service.invite_user_by_email(channel_id, email, name)
        if not invited:
            # 워크스페이스에 아직 가입하지 않은 경우 team_join을 위해 펜딩으로 이관
            add_pending(email, name, channel_id)
            # 가입 링크 이메일 발송
            if Config.SLACK_INVITE_URL:
                send_invite_email(email, name, Config.SLACK_INVITE_URL)
            
        # 지정된 채널에 PDF 파일 업로드 (각각 고유한 버전을 가진 타이틀로 매핑)
        if local_task_pdf:
            slack_service.upload_file(channel_id, local_task_pdf, title=local_task_filename)
        if local_onboard_pdf:
            slack_service.upload_file(channel_id, local_onboard_pdf, title=local_onboard_filename)
        else:
            temp_onboarding = os.path.join(Config.DOWNLOAD_DIR, "신입사원_온보딩_안내.txt")
            with open(temp_onboarding, "w", encoding="utf-8") as f:
                f.write(f"안녕하세요 {name}님!\n본 채널에 합류하신 것을 환영합니다.\n가이드 문서를 확인해 주세요.")
            slack_service.upload_file(channel_id, temp_onboarding, title="신입사원_온보딩_안내.txt")

        # 환영 및 챗봇 가이드 메시지 발송
        welcome_text = (
            f"🎉 **환영합니다! {name}님** 🎉\n\n"
            f"본 채널은 신입 근로자의 온보딩 가이드를 지원하기 위한 채널입니다.\n"
            f"채널에 업로드된 과업 가이드를 다운로드하여 꼼꼼히 확인해 주시기 바랍니다.\n\n"
            f"💡 **업무 질문이 있으신가요?**\n"
            f"본 채널에서 저를 언급하거나 `@Auto_Bot1 [질문내용]` 형태로 질문하시면 최신 업로드된 PDF를 기반으로 24시간 실시간 답변을 지원합니다!\n"
            f"예시: `@Auto_Bot1 과업 일정이 어떻게 되나요?`"
        )
        slack_service.send_message(channel_id, welcome_text)

    background_tasks.add_task(process_pipeline)
    return {"status": "success", "message": f"{name}님의 온보딩 및 파일 임베딩 파이프라인을 시작합니다."}

@app.post("/onboard")
async def onboard_worker(request: OnboardRequest, background_tasks: BackgroundTasks):
    local_pdf = os.path.join(Config.BASE_DIR, "2. 과업지시서.pdf")
    if os.path.exists(local_pdf):
        rag_service.index_pdf(local_pdf)
        
    async def run_onboarding_process():
        email_prefix = request.email.split('@')[0].lower()
        clean_prefix = "".join([c if c.isalnum() or c == '-' else '-' for c in email_prefix])
        channel_name = f"ot-proj-{clean_prefix}"
        
        channel_id = slack_service.create_channel(channel_name)
        if not channel_id:
            print(f"Failed to create or find channel: {channel_name}")
            return
            
        if Config.SMTP_USER:
            slack_service.invite_user_by_email(channel_id, Config.SMTP_USER, "관리자")
            
        invited = slack_service.invite_user_by_email(channel_id, request.email, request.name)
        if not invited:
            add_pending(request.email, request.name, channel_id)
            if Config.SLACK_INVITE_URL:
                send_invite_email(request.email, request.name, Config.SLACK_INVITE_URL)
        
        if os.path.exists(local_pdf):
            slack_service.upload_file(channel_id, local_pdf, title="과업지시서.pdf")
        
        onboarding_pdf = os.path.join(Config.BASE_DIR, "온보딩.pdf")
        if os.path.exists(onboarding_pdf):
            slack_service.upload_file(channel_id, onboarding_pdf, title="온보딩.pdf")
        else:
            temp_onboarding = os.path.join(Config.DOWNLOAD_DIR, "온보딩_안내.txt")
            with open(temp_onboarding, "w", encoding="utf-8") as f:
                f.write(f"안녕하세요 {request.name}님!\n본 채널은 '{request.project_name}' 과업 수행을 위한 온보딩 공간입니다.\n상단의 과업지시서를 확인하시고, 궁금한 점은 이 채널에서 챗봇을 언급하여 질문하세요.")
            slack_service.upload_file(channel_id, temp_onboarding, title="온보딩_안내.txt")

        welcome_text = (
            f"🎉 **환영합니다! {request.name}님** 🎉\n\n"
            f"**'{request.project_name}'** 과업 수행을 위해 생성된 채널입니다.\n"
            f"채널에 업로드된 과업지시서 파일을 꼼꼼히 확인해 주시기 바랍니다.\n\n"
            f"💡 **업무 질문이 있으신가요?**\n"
            f"본 채널에서 저를 언급하거나 `@Auto_Bot1 [질문내용]` 형태로 질문하시면 과업지시서 내용을 바탕으로 24시간 실시간 답변을 지원합니다!\n"
            f"예시: `@Auto_Bot1 과업 일정이 어떻게 되나요?`"
        )
        slack_service.send_message(channel_id, welcome_text)

    background_tasks.add_task(run_onboarding_process)
    return {"status": "success", "message": f"{request.name}님의 온보딩 프로세스를 백그라운드에서 실행합니다."}

async def run_post_join_onboarding(user_id: str, email: str, name: str, channel_name: str):
    await asyncio.sleep(2)
    
    # 🌟 2중 방어 조치: 채널명이 고유 ID 포맷인지 검증 후 처리 고도화
    if channel_name.startswith("C") and len(channel_name) >= 9:
        channel_id = channel_name
    else:
        # 채널명이 ID가 아닌 문자열 이름으로 들어왔을 경우를 위한 완벽 폴백 안전장치
        channel_id = None
        try:
            channels = slack_service.list_public_channels()
            target_slug = channel_name.lower().replace(" ", "-")
            for ch in channels:
                if ch["name"] == target_slug:
                    channel_id = ch["id"]
                    break
        except Exception as e:
            print(f"Error resolving channel name fallback: {e}")
            
    if not channel_id:
        print(f"Error: Target channel {channel_name} not found for user {email}")
        return
        
    real_channel_name = slack_service.get_channel_name_by_id(channel_id)
        
    try:
        slack_service.client.conversations_invite(channel=channel_id, users=user_id)
        print(f"[SUCCESS] Invited new user {name} ({user_id}) directly to channel {channel_id}")
    except Exception as invite_err:
        print(f"[WARNING] Failed to invite user directly: {invite_err}. Attempting fallback via email...")
        slack_service.invite_user_by_email(channel_id, email, name)
    
    local_pdf = os.path.join(Config.BASE_DIR, "2. 과업지시서.pdf")
    if os.path.exists(local_pdf):
        rag_service.index_pdf(local_pdf)
        slack_service.upload_file(channel_id, local_pdf, title="과업지시서.pdf")
        
    onboarding_pdf = os.path.join(Config.BASE_DIR, "신입사원 온보딩.pdf")
    if os.path.exists(onboarding_pdf):
        rag_service.index_pdf(onboarding_pdf)
        slack_service.upload_file(channel_id, onboarding_pdf, title="신입사원 온보딩.pdf")
    else:
        temp_onboarding = os.path.join(Config.DOWNLOAD_DIR, "신입사원_온보딩_안내.txt")
        with open(temp_onboarding, "w", encoding="utf-8") as f:
            f.write(f"안녕하세요 {name}님!\n프로젝트 방 #{real_channel_name} 가입을 환영합니다.\n가이드라인 문서를 확인해 주세요.")
        slack_service.upload_file(channel_id, temp_onboarding, title="신입사원_온보딩_안내.txt")

    welcome_prompt = f"""당신은 신입사원의 슬랙 합류를 환영하는 온보딩 담당 챗봇입니다.
신입사원인 '{name}'님이 프로젝트 채널인 '#{real_channel_name}'에 성공적으로 합류했음을 축하하고 격하게 환영하는 메시지를 정중하고 세련된 한국어로 작성해 주세요.
메시지에는 아래 가이드가 포함되어야 합니다:
1. 합류 축하 메시지 및 환영 인사.
2. 채널에 업로드된 과업지시서와 신입사원 온보딩.pdf 파일을 다운로드받아 확인하라는 권장 사항.
3. 채널 안에서 챗봇에게 사내 규칙이나 과업지시서 내용에 대해 실시간으로 질문할 수 있다는 점 안내 (챗봇을 호출할 때의 호출 명칭은 반드시 `@Auto_Bot1`으로 기재할 것).
"""
    try:
        if not Config.GEMINI_API_KEY:
            raise Exception("GEMINI_API_KEY is not set.")
        model = genai.GenerativeModel(Config.GEMINI_MODEL)
        response = model.generate_content(welcome_prompt)
        welcome_text = response.text.strip()
    except Exception as e:
        print(f"Error generating welcome message via Gemini: {e}")
        welcome_text = (
            f"🎉 **환영합니다, {name}님!** 🎉\n\n"
            f"#{real_channel_name} 프로젝트 방에 합류하신 것을 진심으로 축하드립니다.\n"
            f"채널에 업로드된 **과업지시서.pdf**와 **신입사원 온보딩.pdf** 자료를 먼저 확인해주시기 바랍니다.\n\n"
            f"💡 **업무 질문 방법**:\n"
            f"사내 지식 DB(RAG) 기반의 질문 답변을 원하시면, `@Auto_Bot1`을 언급하며 편하게 물어보세요!"
        )

    slack_service.send_message(channel_id, welcome_text)

def async_rag_chat_process(channel_id: str, clean_text: str, thread_ts: str):
    """Heavy한 Ollama 연산을 메인 스레드 방해 없이 백그라운드에서 처리"""
    print(f"[Background Process Start] Query: '{clean_text}'")
    context = rag_service.retrieve_context(clean_text)
    answer = rag_service.generate_answer(clean_text, context)
    slack_service.send_message(channel_id, answer, thread_ts=thread_ts)
    print("[Background Process Complete] Answer sent to Slack.")

@app.post("/slack/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    """슬랙 Event API Webhook 수신 엔드포인트"""
    payload = await request.json()
    
    # 1. URL Verification (Challenge 처리)
    if "challenge" in payload:
        return PlainTextResponse(content=payload["challenge"])
        
    # 슬랙의 네트워크 지연 재시도(Retry) 신호 강제 차단
    if request.headers.get("X-Slack-Retry-Num"):
        print(f"[Slack Retry Ignored] Count: {request.headers.get('X-Slack-Retry-Num')}")
        return {"status": "retry_ignored"}
        
    event = payload.get("event", {})
    event_type = event.get("type")
    channel_id = event.get("channel")
    
    # 봇 자신의 메시지 루프 방지
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return {"status": "ignored", "reason": "bot message"}

    # 신규 워크스페이스 멤버 가입 감지 (team_join)
    if event_type == "team_join":
        user_info = event.get("user", {})
        user_id = user_info.get("id")
        profile = user_info.get("profile", {})
        email = profile.get("email")
        name = profile.get("real_name") or user_info.get("name")
        
        if not email:
            try:
                res = slack_service.client.users_info(user=user_id)
                user_data = res.get("user", {})
                email = user_data.get("profile", {}).get("email")
                if not name:
                    name = user_data.get("real_name") or user_data.get("name")
            except Exception as e:
                print(f"Error fetching user info for team_join user {user_id}: {e}")
                
        if email:
            # 🌟 대소문자 미스매칭 차단 로직 적용
            pending_data = pop_pending(email)
            if pending_data:
                target_channel = pending_data["channel_name"]
                print(f"Detected team_join for {email}. Assigning to channel #{target_channel}...")
                background_tasks.add_task(
                    run_post_join_onboarding, user_id, email, name, target_channel
                )
        return {"status": "processing_team_join"}

    # app_mention과 message의 중복 가동 구조적 차단
    is_dm = channel_id.startswith("D") if channel_id else False
    
    # 채널(C)일 때는 오직 app_mention만 통과, DM(D)일 때는 오직 message만 통과
    if (event_type == "app_mention" and not is_dm) or (event_type == "message" and is_dm):
        
        # 🌟 2차 보안: collections.deque 기반 FIFO 중복 필터링 작동
        client_msg_id = event.get("client_msg_id")
        if client_msg_id:
            if client_msg_id in PROCESSED_MSG_IDS:
                print(f"[Duplicate client_msg_id Filtered] ID: {client_msg_id}")
                return {"status": "duplicated_msg_id"}
            PROCESSED_MSG_IDS.append(client_msg_id)

        text = event.get("text", "")
        thread_ts = event.get("thread_ts") or event.get("ts")
        
        clean_text = text
        if f"<@" in text:
            parts = text.split(">")
            if len(parts) > 1:
                clean_text = "".join(parts[1:]).strip()
        
        if clean_text:
            print(f"[Slack Event Received] Routing unique query to background: '{clean_text}'")
            background_tasks.add_task(async_rag_chat_process, channel_id, clean_text, thread_ts)
            
    return {"status": "success"}