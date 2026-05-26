# Google Drive API 연동 과정 (2차 개발 고도화 반영)

## 1. Google Cloud Console 설정 및 서비스 계정 구성
- Google Cloud Console에서 Drive API를 활성화하고, 서비스 계정(Service Account) 생성 및 키(`credentials.json`)를 발급하였습니다.
- **API 권한 범위(Scopes) 상향**: 단순 읽기만 가능하던 `drive.readonly` 권한에서, 신입사원 온보딩용 PDF 업로드 및 버전 관리를 위해 생성/수정/삭제 권한을 포함하는 전체 권한 `https://www.googleapis.com/auth/drive`로 권한 스코프를 확장 설정하였습니다.

## 2. Drive Service 구현 및 예외 복구 (`drive_service.py`)
- **지연 초기화 (Lazy Initialization)**: `main.py` 구동 단계에서 구글 API 인증 토큰 이슈로 인해 전체 웹 서버가 기동 실패하는 에러를 방지하고자, 최초 비동기 업로드/다운로드 요구가 발생할 때 드라이브 서비스를 초기화(`get_drive_service()`)하도록 구조화했습니다.
- **토큰 자동 갱신**: `token.json` 파일에 저장된 OAuth 2.0 클라이언트 정보를 기반으로, 만료된 액세스 토큰을 백그라운드에서 감지하고 리프레시 토큰을 사용해 무중단 자동 갱신(`creds.refresh(Request())`) 처리를 수행합니다.

## 3. 버전 관리 연동 파일 업로드
- 백엔드 웹 폼에서 접수되어 넘버링이 완료된 파일 경로(예: `2. 과업지시서.ver02.pdf`)를 수신받아 `MediaFileUpload` 및 `files().create()` API로 구글 드라이브에 안전하게 업로드합니다.
- 업로드 시 `parents` 메타데이터에 온보딩 공유 폴더 ID를 지정하여, 버전별(History) 파일이 하나의 폴더에 체계적으로 모여 관리될 수 있도록 연계하였습니다.
