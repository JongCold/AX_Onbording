import os
import sys
from config import Config
from rag_service import RAGService
from slack_service import SlackService

def test_rag_flow():
    print("=== [1] RAG 서비스 테스트 시작 ===")
    rag = RAGService()
    
    # 1.1 local 과업지시서.pdf 경로 확인 및 인덱싱 테스트
    pdf_path = os.path.join(Config.BASE_DIR, "2. 과업지시서.pdf")
    if not os.path.exists(pdf_path):
        print(f"오류: c:\\auto_onbording\\2. 과업지시서.pdf 파일이 없습니다. 현재 경로: {pdf_path}")
        return
        
    print(f"로컬 PDF 파일 분석 중: {pdf_path}")
    rag.index_pdf(pdf_path)
    
    # 1.2 Retrieval (검색) 테스트
    test_queries = [
        "과업 수행 기간은 어떻게 되나요?",
        "현지 도쿄에서 하는 일정은 무엇인가요?",
        "제출해야 하는 결과물 목록을 말해주세요."
    ]
    
    print("\n[검색 및 답변 생성 테스트]")
    for query in test_queries:
        print(f"\n질문: {query}")
        context = rag.retrieve_context(query)
        print(f"-> 검색된 컨텍스트 길이: {len(context)} 자")
        
        # Ollama 모델 정보가 있는 경우 실제 답변 생성 시도
        if Config.OLLAMA_MODEL:
            answer = rag.generate_answer(query, context)
            print(f"-> 생성된 답변:\n{answer}")
        else:
            print("-> [안내] OLLAMA_MODEL이 설정되지 않아 LLM 답변 생성을 스킵합니다.")

def test_slack_flow():
    print("\n=== [2] 슬랙 API 연동 테스트 시작 ===")
    if not Config.SLACK_BOT_TOKEN:
        print("-> [안내] SLACK_BOT_TOKEN이 설정되지 않아 슬랙 테스트를 스킵합니다.")
        return
        
    slack = SlackService()
    test_channel_name = "test-onboarding-bot-channel"
    
    # 2.1 채널 생성 테스트
    print(f"임시 채널 생성 시도: #{test_channel_name}")
    channel_id = slack.create_channel(test_channel_name)
    
    if channel_id:
        print(f"채널 생성 성공! ID: {channel_id}")
        
        # 2.2 메시지 전송 테스트
        msg_ts = slack.send_message(channel_id, "🤖 온보딩 시스템 통합 테스트 메시지입니다.")
        if msg_ts:
            print(f"메시지 발송 성공 (TS: {msg_ts})")
            
            # 스레드 답변 테스트
            slack.send_message(channel_id, "이 답변은 스레드 형태로 작성됩니다.", thread_ts=msg_ts)
            
        # 2.3 파일 업로드 테스트
        pdf_path = os.path.join(Config.BASE_DIR, "2. 과업지시서.pdf")
        if os.path.exists(pdf_path):
            success = slack.upload_file(channel_id, pdf_path, title="[테스트] 과업지시서")
            print(f"파일 업로드 결과: {'성공' if success else '실패'}")
    else:
        print("채널 생성에 실패했습니다. 슬랙 토큰 권한을 확인하세요.")

if __name__ == "__main__":
    print("온보딩 AX 시스템 로컬 통합 테스트 스크립트 실행")
    print(f"프로젝트 기본 디렉토리: {Config.BASE_DIR}")
    
    # RAG 테스트
    test_rag_flow()
    
    # 슬랙 테스트
    test_slack_flow()
    
    print("\n=== 테스트 시나리오 종료 ===")
