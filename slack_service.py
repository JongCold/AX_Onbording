import os
import json
import math
import re
from slack_sdk import WebClient
from config import Config

class SlackService:
    def __init__(self):
        self.client = WebClient(token=Config.SLACK_BOT_TOKEN)
        
        # 봇의 고유 User ID 확인 (유저 토큰 가동 시 봇 초대 목적)
        try:
            auth_info = self.client.auth_test()
            self.bot_user_id = auth_info.get("user_id")
            print(f"🤖 [Slack Bot 인스턴스] 봇 사용자 ID 식별 완료: {self.bot_user_id}")
        except Exception as e:
            print(f"⚠️ 봇 토큰 권한 테스트 실패 (정상적인 API 호출이 제한될 수 있음): {e}")
            self.bot_user_id = None

    def ensure_bot_in_channel(self, channel_id):
        """봇이 해당 채널에 참여해 있도록 강제 조인 및 유저 토큰을 활용한 초대 2중 방어선"""
        try:
            # 1. 봇 토큰 자체 권한으로 채널 가입 시도 (channels:join 스코프 필요)
            self.client.conversations_join(channel=channel_id)
        except Exception as e:
            # 2. 봇 권한이 막혀있을 경우 .env의 유저 토큰(SLACK_USER_TOKEN)을 활용한 구원 투수 가동
            if Config.SLACK_USER_TOKEN and self.bot_user_id:
                try:
                    user_client = WebClient(token=Config.SLACK_USER_TOKEN)
                    try:
                        user_client.conversations_join(channel=channel_id)
                    except Exception:
                        pass
                    # 유저(대표님 계정)가 방에 들어간 뒤 봇(@Auto_Bot1)을 강제로 초대
                    user_client.conversations_invite(channel=channel_id, users=self.bot_user_id)
                    print(f"✅ [SLACK_USER_TOKEN 사용] 봇({self.bot_user_id})을 채널 {channel_id}에 강제 가입시켰습니다.")
                except Exception as invite_err:
                    print(f"❌ 유저 토큰을 통한 봇 초대 마저 실패했습니다: {invite_err}")
            else:
                if "missing_scope" in str(e):
                    print(f"💡 [안내] channels:join 권한이나 SLACK_USER_TOKEN이 배정되지 않아 봇 자동 조인을 건너뜁니다. (chat:write.public 권한으로 다이렉트 전송 시도)")
                else:
                    print(f"⚠️ 채널 조인 프로세스 예외 발생 ({channel_id}): {e}")

    def create_channel(self, channel_name):
        """슬랙 공개 채널 생성 (이미 존재할 시 기존 채널 ID 반환)"""
        try:
            response = self.client.conversations_create(name=channel_name, is_private=False)
            return response['channel']['id']
        except Exception as e:
            if "name_taken" in str(e):
                try:
                    # 이미 사용 중인 채널명일 경우 전체 채널 목록을 순회하여 고유 ID 탐색
                    channels = self.client.conversations_list(types="public_channel,private_channel", limit=200)
                    for ch in channels['channels']:
                        if ch['name'] == channel_name:
                            return ch['id']
                except Exception as list_err:
                    print(f"🚨 채널 목록 리스트 조회 실패: {list_err}")
            print(f"🚨 슬랙 채널 '{channel_name}' 생성 실패: {e}")
            return None

    def invite_user_by_email(self, channel_id, email, name=None):
        """이메일 기반 슬랙 채널 초대 처리 (★ 중복 데이터 파일 쓰기 로직 제거하여 UI 매핑 버그 원천 차단)"""
        # 작동 전 봇이 방에 들어와 있는지 권한 선행 확인
        self.ensure_bot_in_channel(channel_id)
        
        try:
            # 1. 이메일로 유저 슬랙 고유 ID 매핑 조회
            user_info = self.client.users_lookupByEmail(email=email)
            user_id = user_info['user']['id']
            
            # 2. 채널 내부로 유저 최종 초대
            self.client.conversations_invite(channel=channel_id, users=user_id)
            print(f"✅ 슬랙 채널 {channel_id} 내부로 사원 {name if name else email} 초대 완료.")
            return True
        except Exception as invite_err:
            # 워크스페이스 미가입 사원 혹은 권한 초과 시 무너졌던 구조를 정상 에러 핸들링으로 우회
            print(f"ℹ️ {email} 사원은 현재 워크스페이스 미가입 상태이거나 초대할 수 없습니다. (대기자 DB 자동 이관용): {invite_err}")
            return False

    def upload_file(self, channel_id, file_path, title=None):
        """채널 내부에 과업 가이드라인 PDF 파일 업로드 (v2 최신 규격 반영)"""
        self.ensure_bot_in_channel(channel_id)
        try:
            if not os.path.exists(file_path):
                print(f"❌ 업로드 대상 파일이 로컬 경로에 존재하지 않습니다: {file_path}")
                return False
                
            self.client.files_upload_v2(
                channel=channel_id,
                file=file_path,
                title=title
            )
            print(f"▲ [File Uploaded] {title if title else file_path} -> 채널: {channel_id}")
            return True
        except Exception as e:
            print(f"🚨 슬랙 파일 업로드 API 오류 발생: {e}")
            return False

    def send_message(self, channel_id, text, thread_ts=None):
        """슬랙 일반 메시지 혹은 특정 대화 스레드 내부 답글(RAG용) 실시간 발송"""
        self.ensure_bot_in_channel(channel_id)
        try:
            response = self.client.chat_postMessage(
                channel=channel_id,
                text=text,
                thread_ts=thread_ts
            )
            return response['ts']
        except Exception as e:
            print(f"🚨 슬랙 메시지 발송 오류 발생: {e}")
            return None

    def list_public_channels(self):
        """워크스페이스 내 모든 활성화된 공개 채널 목록 조회 (이름 가나다순 정렬 및 난수형 ID 채널 원천 필터링)"""
        # 9자리 이상의 영어 소문자와 숫자로만 구성된 슬랙 고유 ID 형태의 채널명(예: c0b5t8f7vss) 필터링
        garbage_pattern = re.compile(r'^[a-z0-9]{9,}$')
        try:
            response = self.client.conversations_list(types="public_channel", exclude_archived=True, limit=100)
            channels = response.get("channels", [])
            channel_list = []
            
            for ch in channels:
                name = ch["name"]
                # 봇 생성 시 자동 개설된 난수형 임시 채널은 UI 목록에서 제외
                if garbage_pattern.match(name):
                    continue
                channel_list.append({"id": ch["id"], "name": name})
                
            # 대시보드 화면에 보기 편하게 채널 가나다순(알파벳순) 정렬 처리
            return sorted(channel_list, key=lambda x: x["name"])
        except Exception as e:
            print(f"🚨 워크스페이스 공개 채널 목록 호출 실패: {e}")
            return []

    def get_channel_name_by_id(self, channel_id):
        """채널 고유 ID를 기반으로 실제 슬랙 UI 표기명 역조회"""
        try:
            res = self.client.conversations_info(channel=channel_id)
            return res.get("channel", {}).get("name", channel_id)
        except Exception as e:
            print(f"🚨 채널 ID {channel_id} 명칭 역조회 실패: {e}")
            return channel_id