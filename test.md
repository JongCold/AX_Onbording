graph TD
    %% 스타일 정의
    classDef inputStyle fill:#e1f5fe,stroke:#0288d1,stroke-width:2px,color:#01579b;
    classDef processStyle fill:#ffffff,stroke:#333333,stroke-width:2px,color:#000000;
    classDef logicStyle fill:#fff3e0,stroke:#ffb74d,stroke-width:2px,color:#e65100;
    classDef hitlStyle fill:#f3e5f5,stroke:#ba68c8,stroke-width:2px,color:#4a148c;
    classDef outputStyle fill:#e8f5e9,stroke:#388e3c,stroke-width:2px,color:#1b5e20;

    %% 1단계: 파이프라인 자동 입력 (Human Intervention 최소화)
    subgraph Inputs [1. 원시 데이터 자동 변환]
        In1["내부보안점검 상시 체크리스트<br>(Excel ➔ Markdown 변환)"]:::inputStyle
        In2["자사 보유 보안 솔루션 목록<br>(Excel ➔ Markdown 변환)"]:::inputStyle
    end

    %% 2단계: RAG 컨텍스트 결합 (도메인 매핑 테이블 및 루브릭 주입)
    subgraph RAG_Engine [2. Vector DB 및 RAG]
        RAG["RAG 검색 증강 엔진"]:::processStyle
        RAG_Ref["• 최신 ISMS-P 심사 가이드라인 문서<br>• 솔루션별 기능 명세서/소개서<br>• 통제항목 - 솔루션 도메인 매핑 테이블<br>• 위험도/시급성 산정 객관적 루브릭(Rubric)"]
        RAG -.-> RAG_Ref
    end

    %% 3단계: sLLM 추론 (컨설턴트 CoT 반영)
    subgraph AI_Reasoning [3. 파인튜닝된 sLLM 추론]
        sLLM["sLLM 모델<br>(Llama 3 8B / Qwen 2.5 7B)"]:::processStyle
        CoT["컨설턴트 CoT (Chain of Thought)<br>맥락 파악 및 1차 솔루션 매핑 안 생성"]
        sLLM -.-> CoT
    end

    %% 4단계: 일정 산정 알고리즘 분기 (인증 규정 충돌 해결 및 정합성 확보)
    subgraph Logic_Gate [4. 로드맵 일정 산정 알고리즘 분기]
        Check_ISMS{"법적/인증<br>필수 결함 항목인가?"}:::logicStyle
        Is_ISMS_Yes["[단기 일정] 최우선 강제 배치<br>(인증 규정 준수: 최대 100일 이내 조치)"]:::logicStyle
        Is_ISMS_No["[단기/중기/장기] 분배<br>(솔루션 가격 + 구축 난이도 기준 산정)"]:::logicStyle
        
        Check_ISMS -- "Yes (인증 결함)" --> Is_ISMS_Yes
        Check_ISMS -- "No (일반 취약점)" --> Is_ISMS_No
    end

    %% 5단계: Human-in-the-Loop (검토 단계를 AI 추론 이후 최종 승인 전으로 이동)
    subgraph HITL_Phase [5. Human-in-the-Loop]
        HITL["컨설턴트 / 보안엔지니어<br>최종 검토 및 UI 보정"]:::hitlStyle
        HITL_Detail["• sLLM이 도출한 1차 로드맵 데이터 검증<br>• 시급성/위험도 및 예상예산 최종 조율/확정"]
        HITL -.-> HITL_Detail
    end

    %% 6단계: 최종 산출물 추출 (오타 수정 반영)
    subgraph Outputs [6. 최종 산출물 추출]
        Out_File["보안 솔루션 로드맵 엑셀 파일<br>(보안 솔루션 로드맵.xlsx)"]:::outputStyle
        Out_Data["포함 데이터 Schema:<br>보안영역 | 과제명 | 법적요구 | 시급성(1~5) | 위험도(1~5) | 예상예산 | 로드맵연도 | 비고"]
        Out_File -.-> Out_Data
    end

    %% 데이터 흐름 연결
    In1 --> RAG
    In2 --> RAG
    RAG --> sLLM
    sLLM --> Check_ISMS
    Check_ISMS --> Is_ISMS_Yes
    Check_ISMS --> Is_ISMS_No
    Is_ISMS_Yes --> HITL
    Is_ISMS_No --> HITL
    HITL --> Out_File
