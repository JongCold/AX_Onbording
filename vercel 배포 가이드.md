# Vercel 프론트엔드 배포 가이드

본 가이드는 대표자(관리자)용 온보딩 대시보드 웹 인터페이스를 무료 호스팅 서비스인 Vercel에 단독 배포하고, 로컬에서 실행 중인 FastAPI 백엔드 서버(Ngrok 터널링)와 안전하게 연동하는 방법을 기술합니다.

---

## 1. 연동 설계 방식 (아키텍처)
FastAPI 백엔드는 로컬 파일 저장 및 RAG 벡터 DB(`vector_db.json`), Ollama 인프라 가동을 위해 **대표님의 로컬 개발 PC**에서 계속 구동됩니다. 
대신, 외부 사용자(대표/고객)가 쉽게 접속하여 근로자를 등록할 수 있도록 **정적 프론트엔드 페이지(`static/` 폴더)**만 Vercel에 배포하여 연결합니다.

- **프론트엔드**: Vercel에 배포 (`https://[프로젝트명].vercel.app`)
- **백엔드**: 대표님 PC에서 구동 (`https://seducing-issue-overflow.ngrok-free.dev`)

> [!NOTE]
> 코드에 **동적 라우팅 분기 처리**가 이미 적용되어 있어, 로컬 테스트 환경(`localhost`, `127.0.0.1`)에서는 상대 경로로 로컬 서버와 즉시 통신하며, Vercel 상에서는 자동으로 설정된 고정 `Ngrok` 주소로 연동을 시도합니다. 백엔드 코드에도 외부 접근을 허용하기 위한 CORS(Cross-Origin Resource Sharing) 설정이 적용 완료되었습니다.

---

## 2. GitHub 저장소로 코드 푸시하기

먼저, 로컬의 변경 사항을 대표님의 GitHub 저장소(`https://github.com/JongCold/AX_Onbording.git`)로 업로드(Push)해야 합니다.

1. **로컬 터미널에서 Git 초기화 및 파일 스테이징**
   ```bash
   # 로컬 프로젝트 루트(c:\auto_onbording)에서 실행
   git add .
   ```
2. **커밋 생성**
   ```bash
   git commit -m "feat: CORS 활성화 및 Vercel 프론트엔드 연동 지원을 위한 동적 라우팅 설정"
   ```
3. **GitHub 원격 저장소로 푸시**
   ```bash
   # 기본 브랜치를 main(또는 master)으로 설정한 뒤 푸시
   git branch -M main
   git push -u origin main
   ```
   *(※ 푸시 시 GitHub 로그인 또는 개인 액세스 토큰(PAT) 인증이 요구될 수 있습니다.)*

---

## 3. Vercel에 프론트엔드 배포 설정하기

코드 푸시가 완료되면, Vercel 대시보드에서 다음과 같이 프로젝트를 연동하여 배포를 완료합니다.

1. **Vercel 대시보드 접속 및 로그인**
   - [Vercel](https://vercel.com/) 사이트에 접속하여 로그인합니다. (GitHub 계정 로그인을 권장합니다.)

2. **새 프로젝트 생성**
   - **`Add New...`** -> **`Project`** 버튼을 클릭합니다.
   - 대표님의 GitHub 계정을 연동한 뒤, **`AX_Onbording`** 저장소를 찾아서 **`Import`** 버튼을 클릭합니다.

3. **배포 환경 설정 (중요 🌟)**
   - Vercel은 기본적으로 루트 디렉터리의 전체 파일을 빌드하려고 시도합니다. 우리는 오직 `static` 폴더 내의 파일들만 외부에 웹사이트로 서비스할 것이므로 다음 설정을 반드시 적용해야 합니다:
     - **Framework Preset**: `Other`로 설정 (또는 디폴트 유지)
     - **Root Directory**: `static` 으로 변경 (또는 `Edit` 버튼을 클릭하여 `static` 폴더를 직접 선택)
     - **Build and Development Settings**: 기본값 그대로 둡니다. (Build Command나 Output Directory를 수정할 필요가 없습니다.)
   
4. **배포 시작**
   - **`Deploy`** 버튼을 클릭합니다.
   - 1분 내외로 빌드가 완료되고, Vercel에서 제공하는 고유한 무료 도메인 주소(예: `https://ax-onbording-xxxx.vercel.app`)가 생성됩니다.

---

## 4. 최종 작동 확인 및 유의 사항
1. **로컬 백엔드 서버 가동**: 대표님 PC에서 FastAPI 서버를 반드시 띄워 놓아야 합니다.
   ```bash
   uvicorn main:app --port 8000
   ```
2. **Ngrok 터널 가동**: 외부 통신을 위해 ngrok도 함께 백그라운드에 켜져 있어야 합니다.
3. 배포된 Vercel 도메인으로 브라우저에 접속하여 신입사원 이름, 이메일, 그리고 채널(`🆕 [새로운 전용 채널 자동 생성하여 진행]`)을 선택해 파일 업로드를 진행해 봅니다.
4. 로컬 터미널 및 슬랙에 정상적으로 파이프라인(구글 드라이브 업로드 ➡️ RAG 인덱싱 ➡️ 슬랙 초대 및 PDF 배포)이 기동되는지 확인합니다.
