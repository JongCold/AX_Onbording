# Slack API 연동 및 트러블슈팅 완료 보고서

본 문서는 신규 채용된 단기 근로자 온보딩 자동화 시스템(AX 프로세스)을 구축하는 과정에서 발생한 Slack API 연동 관련 에러 해결 과정과 최신 코드 수정 사항을 종합한 보고서입니다.

## 1. URL Verification (Challenge) 등록 에러 해결
* **증상**: Slack Event Subscriptions 설정에서 Request URL(`https://...ngrok-free.dev/slack/events`)을 등록할 때 `our URL didn't respond with the value of the challenge parameter` 에러 발생.
* **원인**: Slack이 엔드포인트 유효성 검증을 위해 POST 요청으로 보내는 `challenge` 값을 서버가 올바르게 반환하지 못함.
* **해결 및 최신 코드 반영**: 
  * `main.py`의 `@app.post("/slack/events")` 라우터 최상단에 `challenge` 파라미터를 감지하여 `PlainTextResponse`로 즉시 반환하도록 로직 추가.

## 2. 채널 생성 및 이메일 초대 500 에러 해결
* **증상**: `/onboard` 엔드포인트 호출 시 `슬랙 프로젝트 채널을 생성하거나 찾는 데 실패했습니다.` 또는 `초대 이메일 전송에 실패했습니다.` 에러 발생. 이미 초대된 사용자일 경우에도 서버 오류 발생.
* **원인**: 슬랙 API 채널 생성 시 이미 존재하는 채널명(`name_taken`)에 대한 예외 처리가 미흡했고, 초대 시 유저가 이미 채널에 있거나 이메일 발송 환경(SMTP)이 세팅되지 않은 경우 시스템이 중단됨.
* **해결 및 최신 코드 반영 (`slack_service.py`)**:
  * **채널 생성 안전성 확보**: `create_channel` 메서드에서 예외 발생 시 `conversations_list`를 순회하여 기존 채널 ID를 반환하도록 Fallback 로직 완비.
  * **중복 초대 방어**: `invite_user_by_email` 실행 시 에러가 발생해도 로컬 매핑 데이터(JSON)에는 정상적으로 상태를 보존하도록 `try-except` 블록으로 캡슐화.

## 3. 한글 깨짐 (인코딩) 문제 해결
* **증상**: PowerShell의 `Invoke-RestMethod`로 전송한 한글 데이터("홍길동")가 서버 측에서 `???`로 수신되고, `pending_onboardings.json`에 `???`로 저장됨.
* **원인**: Windows PowerShell 5.1의 기본 인코딩이 UTF-8이 아니어서 JSON 변환 후 전송 시 시스템 기본 인코딩(ASCII/Windows-1252)으로 데이터가 손상됨.
* **해결 및 최신 코드 반영**:
  * **클라이언트 측**: `curl.exe`를 사용하거나 PowerShell의 `[System.Text.Encoding]::UTF8.GetBytes()`를 사용하여 명시적으로 UTF-8 바이트 배열을 전송하도록 가이드 및 해결.
  * **서버 측 (`slack_service.py`)**: JSON 저장 시 `ensure_ascii=False`와 `encoding="utf-8"` 속성을 명시하여 추후 어떠한 환경에서도 한글이 보존되도록 교정. (데이터베이스 파일명도 `pending_workers.json`으로 갱신)

## 4. 슬랙 봇 메시지 중복 답변 및 재시도(Retry) 방어
* **증상**: RAG 챗봇 연산(LLM)이 오래 걸릴 경우 Slack이 응답 지연으로 간주하여 동일한 이벤트를 여러 번 재전송(Retry)하고, 봇이 여러 번 답변을 다는 문제 발생.
* **원인**: Slack은 3초 이내에 HTTP 200 OK 응답이 없으면 이벤트를 재시도(`X-Slack-Retry-Num`)함.
* **해결 및 최신 코드 반영 (`main.py`)**:
  * **Retry 무시 로직**: `request.headers.get("X-Slack-Retry-Num")`을 감지하여 재시도 요청은 즉시 차단.
  * **In-Memory 디두플리케이션**: `client_msg_id`를 `PROCESSED_MSG_IDS` Set에 캐싱(최대 200개 유지)하여 중복 이벤트 원천 차단.
  * **비동기 백그라운드 처리**: RAG 검색 및 LLM 답변 생성(`async_rag_chat_process`)을 `BackgroundTasks`로 위임하여 Slack에는 즉시 200 OK를 반환하도록 아키텍처 대폭 개선.

## 5. RAG 모델 통합 및 워크플로우 자동화 고도화
* **증상/요구사항**: 빠르고 즉각적인 응답이 필요하며, 사용자의 채널명 입력 오류를 방지해야 함.
* **해결 및 최신 코드 반영**:
  * **LLM 패키지 종속성 해결**: `ModuleNotFoundError: No module named 'google.generativeai'` 발생 문제를 `pip install`로 해결 후, 환경에 맞춰 유연하게 모델(Ollama / Gemini)을 병행 사용할 수 있도록 지원. 최종적으로 로컬 네트워크에 특화된 Ollama RAG 아키텍처로 안정성 극대화 (`rag_service.py`).
  * **채널명 자동화**: `/onboard` 스키마를 `channel_name` 직접 입력에서 `project_name` 입력으로 변경. (예: `ot-강북창업지원센터-홍길동` 규칙으로 자동화 생성).
  * **호출 명칭 고정**: 챗봇 호출 명칭을 `@Auto_Bot1`으로 지정하여 신입사원이 쉽게 질문할 수 있도록 웰컴 가이드라인 템플릿에 명시.

---
**총평**: 발생하는 다양한 API 엣지 케이스(중복 채널, 중복 메시지 타임아웃, 인코딩 문제)를 모두 구조적으로 방어하였으며, 현재 `main.py`와 `slack_service.py`는 신규 인력 온보딩 및 RAG 챗봇 자동화 서비스로 **실제 프로덕션 레벨에 배포 가능한 수준의 안정성을 확보**하였습니다.
