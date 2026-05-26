import os
import json
import math
from pypdf import PdfReader
import requests
from config import Config

class RAGService:
    def __init__(self):
        # JSON 기반 초경량 로컬 벡터 스토어 경로 설정
        self.db_path = os.path.join(Config.CHROMA_DB_DIR, "vector_db.json")
        self.documents_db = self._load_db()
        print(f"📦 [로컬 RAG 엔진] 가동 완료 (임베딩: {Config.OLLAMA_EMBED_MODEL} / LLM: {Config.OLLAMA_MODEL})")

    def _load_db(self) -> list:
        """JSON 데이터베이스 파일 로드"""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"🚨 [ERROR] 벡터 DB 로드 실패: {e}")
                return []
        return []

    def _save_db(self):
        """JSON 데이터베이스 파일 저장"""
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self.documents_db, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"🚨 [ERROR] 벡터 DB 저장 실패: {e}")

    def _get_embedding(self, text: str) -> list:
        """순수 로컬 Ollama API를 사용하거나 실패 시 Gemini API를 활용하여 768차원 임베딩 벡터 생성"""
        # 1. Ollama /api/embed (최신 규격) 호출 시도 (타임아웃 10초로 보완)
        try:
            url = f"{Config.OLLAMA_BASE_URL}/api/embed"
            payload = {
                "model": Config.OLLAMA_EMBED_MODEL,
                "input": text
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                res_data = response.json()
                embeddings = res_data.get("embeddings")
                if embeddings and len(embeddings) > 0:
                    return embeddings[0]
        except Exception:
            pass

        # 2. Ollama /api/embeddings (구 규격) 호출 시도
        try:
            url = f"{Config.OLLAMA_BASE_URL}/api/embeddings"
            payload = {
                "model": Config.OLLAMA_EMBED_MODEL,
                "prompt": text
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                res_data = response.json()
                embedding = res_data.get("embedding")
                if not embedding and "embeddings" in res_data and len(res_data["embeddings"]) > 0:
                    embedding = res_data["embeddings"][0]
                if embedding:
                    return embedding
        except Exception:
            pass

        # 3. Gemini API 기반 임베딩 폴백 (Ollama 일시적 중단 대비 방어선)
        if Config.GEMINI_API_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=Config.GEMINI_API_KEY)
                res = genai.embed_content(
                    model="models/text-embedding-004",
                    content=text,
                    task_type="retrieval_document"
                )
                embedding = res.get("embedding")
                if embedding:
                    return embedding
            except Exception as e:
                print(f"🚨 [ERROR] Gemini 임베딩 폴백 실패: {e}")

        print("⚠️ [WARNING] 모든 임베딩 생성 시도가 실패하여 디폴트 제로 벡터(768차원)를 할당합니다.")
        return [0.0] * 768

    def _cosine_similarity(self, v1: list, v2: list) -> float:
        """두 벡터 간의 코사인 유사도 정밀 계산"""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        
        # 제로 벡터가 들어올 경우 연산 예외 처리
        if all(x == 0.0 for x in v1) or all(x == 0.0 for x in v2):
            return 0.0
            
        dot_product = sum(x * y for x, y in zip(v1, v2))
        norm_v1 = math.sqrt(sum(x ** 2 for x in v1))
        norm_v2 = math.sqrt(sum(x ** 2 for x in v2))
        
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return dot_product / (norm_v1 * norm_v2)

    def extract_text_from_pdf(self, file_path: str) -> list:
        """PDF 파일에서 텍스트를 페이지/단락 단위로 정밀 분할 추출"""
        documents = []
        file_name = os.path.basename(file_path)
        
        try:
            reader = PdfReader(file_path)
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if not text:
                    continue
                
                # 가독성 개선을 위한 공백 정제 및 단락 단위 청킹
                paragraphs = text.strip().split("\n\n")
                current_chunk = ""
                
                for para in paragraphs:
                    para = para.strip()
                    if not para:
                        continue
                    # 로컬 소형 모델(Gemma2)이 컨텍스트를 가장 잘 소화하는 500자 단위 청크 슬라이싱
                    if len(current_chunk) + len(para) < 500:
                        current_chunk += "\n" + para if current_chunk else para
                    else:
                        documents.append({
                            "text": current_chunk,
                            "metadata": {"source": file_name, "page": page_num + 1}
                        })
                        current_chunk = para
                
                if current_chunk:
                    documents.append({
                        "text": current_chunk,
                        "metadata": {"source": file_name, "page": page_num + 1}
                    })
            return documents
        except Exception as e:
            print(f"🚨 [ERROR] PDF 텍스트 추출 중 에러 발생: {e}")
            return []

    def index_pdf(self, file_path: str):
        """PDF 문서를 읽어서 청킹하고 순수 로컬 임베딩 생성 후 인덱싱 데이터 매핑"""
        chunks = self.extract_text_from_pdf(file_path)
        if not chunks:
            print(f"🚨 [ERROR] {file_path} 문서에서 추출된 텍스트가 없습니다.")
            return
        
        file_name = os.path.basename(file_path)
        
        # 파일 중복 인덱싱 방지 전처리
        self.documents_db = [doc for doc in self.documents_db if doc["metadata"]["source"] != file_name]
        
        added_count = 0
        for idx, chunk in enumerate(chunks):
            chunk_text = chunk["text"]
            
            emb = self._get_embedding(chunk_text)
            # 유효하지 않은 제로 벡터는 인덱싱에서 제외
            if all(x == 0.0 for x in emb):
                continue
                
            doc_id = f"{file_name}_{chunk['metadata']['page']}_{idx}"
            self.documents_db.append({
                "id": doc_id,
                "document": chunk_text,
                "embedding": emb,
                "metadata": chunk["metadata"]
            })
            added_count += 1
            
        self._save_db()
        print(f"✅ [SUCCESS] [Ollama Indexing] {file_name} 로부터 {added_count}개의 데이터 청크를 로컬 벡터 DB에 빌드 완료.")

    def retrieve_context(self, query: str, n_results: int = 3) -> str:
        """사용자 질문 벡터와 코사인 유사도가 가장 높은 상위 문맥 단락 검색"""
        # 🌟 개발자님 지침 반영: 온보딩 관련 종합 질의 시 청크 검색 범위를 6개로 자동 확장
        if "온보딩" in query:
            n_results = 6

        query_emb = self._get_embedding(query)
        if not self.documents_db or all(x == 0.0 for x in query_emb):
            return ""
            
        scored_docs = []
        for doc in self.documents_db:
            sim = self._cosine_similarity(query_emb, doc["embedding"])
            scored_docs.append((sim, doc["document"]))
            
        # 유사도 점수 기준 내림차순 정렬
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        
        # 로컬 환경 매칭 최적화를 위해 임계값 조건 필터링 (유사도 0.15 이상만 채택)
        results = [doc_text for score, doc_text in scored_docs[:n_results] if score > 0.15]
        
        if not results:
            return ""
            
        return "\n---\n".join(results)

    def generate_answer(self, query: str, context: str) -> str:
        """로컬 Ollama LLM(Gemma)에 컨텍스트를 주입하여 최종 답변 생성"""
        if not context:
            return "제공된 과업지시서 내에서 질문과 관련된 핵심 내용을 찾지 못했습니다. 번거로우시겠지만 세부 사항은 담당자에게 교차 확인을 부탁드립니다! 😊"

        is_onboarding_request = "온보딩" in query
        onboarding_instruction = ""
        
        if is_onboarding_request:
            # RAG DB 내 고유 소스 파일 리스트 실시간 역추적 파악
            sources = list(set([doc["metadata"]["source"] for doc in self.documents_db if "metadata" in doc and "source" in doc["metadata"]]))
            source_list_str = ", ".join(sources) if sources else "2. 과업지시서.pdf, 신입사원 온보딩.pdf"
            
            # 🌟 개발자님 지침 반영: 온보딩 전용 맞춤형 프롬프트 인젝션
            onboarding_instruction = f"""
[특별 추가 지침]
사용자가 '온보딩'에 관한 종합적인 안내 또는 요약을 요청했습니다.
1. 현재 지식베이스에 업로드되어 분석된 문서 목록인 [{source_list_str}]을 명확히 명시하십시오.
2. 아래 [과업지시서 문맥 정보]를 관통하는 핵심 과업 일정 및 규칙을 분석하여, 각 파일별로 3~4문장 분량의 가독성 좋은 상세 요약본을 문단별로 구분하여 정중하게 제공하십시오.
"""

        prompt = f"""당신은 신규 채용된 근로자의 업무 적응을 돕는 사내 온보딩 OT 담당 AI 조수입니다.
[지침] 아래 제공된 [과업지시서 문맥 정보]만을 철저히 참조하여 사용자의 질문에 정중하고 상냥한 어조의 한국어로 답변하세요.
{onboarding_instruction}
[과업지시서 문맥 정보]
{context}

[사용자 질문]
{query}

답변:"""

        try:
            url = f"{Config.OLLAMA_BASE_URL}/api/generate"
            payload = {
                "model": Config.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            }
            # 🌟 타임아웃 락 해제: 긴 컨텍스트 정독 및 무한 루프 예방을 위해 90초로 안전하게 확장
            response = requests.post(url, json=payload, timeout=90)
            if response.status_code == 200:
                return response.json().get("response", "").strip()
            else:
                return f"❌ 로컬 LLM 엔진이 응답하지 않습니다. (HTTP {response.status_code})"
        except Exception as e:
            return f"🚨 로컬 Ollama 연동 실패. 모델 상태 및 구동 여부를 확인하세요. (오류: {e})"