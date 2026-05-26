import os
import io
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from config import Config

# Google Drive API 권한 범위 (업로드 및 다운로드 권한)
SCOPES = ['https://www.googleapis.com/auth/drive']

class GoogleDriveService:
    def __init__(self):
        self.creds = None
        self.service = None
        # folder_id에 포함된 웹 링크용 쿼리 스트링(?usp=sharing) 자동 정제
        if Config.GOOGLE_DRIVE_FOLDER_ID and '?' in Config.GOOGLE_DRIVE_FOLDER_ID:
            Config.GOOGLE_DRIVE_FOLDER_ID = Config.GOOGLE_DRIVE_FOLDER_ID.split('?')[0]
        self.authenticate()

    def authenticate(self):
        """Google Drive API 인증 및 서비스 빌드"""
        token_path = os.path.join(Config.BASE_DIR, 'token.json')
        
        # 1. 기존 token.json이 존재하면 로드
        if os.path.exists(token_path):
            self.creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            
        # 2. 유효한 자격증명이 없거나 만료된 경우 재인증
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception:
                    self.creds = None
            
            if not self.creds:
                # credentials 정보가 없을 경우 .env에 있는 정보로 credentials.json을 메모리 상에서 구조화
                client_config = {
                    "installed": {
                        "client_id": Config.GOOGLE_CLIENT_ID,
                        "client_secret": Config.GOOGLE_CLIENT_SECRET,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "redirect_uris": ["http://localhost", "http://localhost:8080/"]
                    }
                }
                
                # 로컬 환경에서 브라우저 인증창을 띄워 사용자 동의를 얻음
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                self.creds = flow.run_local_server(port=8080)
                
                # 다음 실행을 위해 토큰을 token.json 파일에 저장
                with open(token_path, 'w') as token:
                    token.write(self.creds.to_json())
                    
        self.service = build('drive', 'v3', credentials=self.creds)

    def list_pdf_files(self, folder_id: str = None) -> list:
        """지정된 폴더 내의 PDF 파일 목록 조회"""
        if not folder_id:
            folder_id = Config.GOOGLE_DRIVE_FOLDER_ID
            
        if not folder_id:
            print("Warning: GOOGLE_DRIVE_FOLDER_ID is not configured.")
            return []

        query = f"'{folder_id}' in parents and mimeType = 'application/pdf' and trashed = false"
        try:
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='nextPageToken, files(id, name, modifiedTime)',
                pageSize=100
            ).execute()
            return results.get('files', [])
        except Exception as e:
            print(f"Error listing files from Google Drive: {e}")
            return []

    def download_file(self, file_id: str, file_name: str) -> str:
        """Google Drive에서 파일을 다운로드하여 로컬에 저장"""
        request = self.service.files().get_media(fileId=file_id)
        file_path = os.path.join(Config.DOWNLOAD_DIR, file_name)
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        
        try:
            while done is False:
                status, done = downloader.next_chunk()
                
            # 다운로드된 바이너리를 파일로 저장
            with open(file_path, 'wb') as f:
                f.write(fh.getvalue())
            
            print(f"Successfully downloaded: {file_name} to {file_path}")
            return file_path
        except Exception as e:
            print(f"Error downloading file {file_name} ({file_id}): {e}")
            return ""

    def upload_file(self, file_path: str, folder_id: str = None) -> str:
        """로컬 파일을 Google Drive에 업로드"""
        if not folder_id:
            folder_id = Config.GOOGLE_DRIVE_FOLDER_ID
            
        if not os.path.exists(file_path):
            print(f"Error: File not found at {file_path}")
            return ""

        file_name = os.path.basename(file_path)
        file_metadata = {
            'name': file_name,
        }
        if folder_id:
            file_metadata['parents'] = [folder_id]

        media = MediaFileUpload(file_path, mimetype='application/pdf', resumable=True)
        try:
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            print(f"Successfully uploaded {file_name} to Google Drive. File ID: {file.get('id')}")
            return file.get('id')
        except Exception as e:
            print(f"Error uploading file {file_name} to Google Drive: {e}")
            return ""
