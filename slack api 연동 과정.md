# Slack API 연동 과정 (2차 개발 고도화 반영)

## 1. 초기 설정 및 권한(Scopes) 구성
- Slack 앱 생성 및 OAuth 토큰 발급 (`SLACK_BOT_TOKEN`, 선택적 `SLACK_USER_TOKEN`).
- 주요 봇 권한(Bot Token Scopes): `chat:write`, `chat:write.public`, `channels:manage`, `channels:read`, `files:write`, `app_mentions:read`, `users:read`, `users:read.email` 등이 설정되어 있습니다.

## 2. 채널 개설 및 유저 초대 프로세스 (`slack_service.py`)
- **채널 자동 개설**: 신입사원 온보딩 시 `conversations.create` API를 통해 전용 채널(`ot-proj-{이메일접두사}`)을 개설합니다.
- **봇 자동 조인 및 유저 토큰 초대 방어선 (`ensure_bot_in_channel`)**:
  - `conversations_join` API로 봇이 채널에 직접 가입을 시도합니다.
  - 만약 `channels:join` 스코프가 누락되어 실패할 경우, `.env`에 설정된 `SLACK_USER_TOKEN` (유저 토큰)을 활용하여 대표 계정이 먼저 채널에 조인한 뒤 봇(`@Auto_Bot1`)을 강제 초대하는 2중 폴백 기능을 갖추고 있습니다.
  - 유저 토큰이 없을 경우, 사용자가 슬랙 상에서 수동으로 봇을 초대하도록 예외 처리와 로그 안내를 구성하였습니다.
- **유저 및 대표자 자동 초대**: `users.lookupByEmail`로 사원 및 대표자 이메일의 ID를 조회 후 `conversations.invite`로 채널에 초대합니다. 미가입 사원의 경우 대기자(Pending) DB로 자동 이관되며, 이메일로 가입 링크를 전송합니다.

## 3. 대시보드 연동 및 신규 채널 생성 분기
- 웹 대시보드 UI에서 기존 채널 선택 뿐만 아니라 **`🆕 [새로운 전용 채널 자동 생성하여 진행]`** 옵션을 선택할 수 있습니다.
- 새로운 전용 채널을 생성하여 진행할 시, 봇이 채널의 생성자(Creator)가 되므로 `channels:join` 권한 및 유저 토큰 없이도 봇이 채널에 귀속되어 `not_in_channel` 에러 없이 파일 업로드와 환영 메시지 발송이 원활하게 성공합니다.

## 4. 파일 업로드 및 환영 메시지 발송
- `files.upload_v2` API를 통해 로컬 스토리지에 임시 저장된 버전 관리형 가이드라인 PDF 파일(`.verxx.pdf`)을 슬랙 채널에 직접 업로드합니다.
- `chat.postMessage` API를 사용하여 웰컴 메시지와 RAG 질문 방법 가이드(Thread 답글 지원)를 발송합니다.

## 5. 이벤트 웹훅 처리 및 중복 방지
- `/slack/events` 웹훅으로 `team_join` 및 멘션(`app_mention`) 이벤트를 수신합니다.
- 슬랙의 재시도(Retry) 호출 및 봇 자신의 메시지 루프를 막기 위해 `client_msg_id` 기반 인메모리 캐시 중복 제거를 적용하고 비동기 백그라운드 태스크로 RAG 질의응답을 처리합니다.
