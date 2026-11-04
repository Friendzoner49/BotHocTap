"""Tải file lên Google Drive của chủ (OAuth, quyền drive.file: chỉ thấy file do chính app này tạo).
credentials.json (từ Google Cloud) và drive_token.json nằm ở thư mục gốc dự án, KHÔNG đưa lên GitHub.
Đăng nhập một lần: dang_nhap_drive.bat. Tải lên dùng resumable nên VPN rớt giữa chừng vẫn thử lại được."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRED = ROOT / "credentials.json"
TOKEN = ROOT / "drive_token.json"
# Quyền «drive» (đầy đủ) để ghi được vào thư mục có sẵn của bạn (theo DRIVE_FOLDER_ID trong .env).
# Code chỉ TẢI LÊN, không đọc/xóa file Drive; nhưng drive_token.json giờ nhạy cảm hơn: không chia sẻ.
SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_NAME = "BotHocTap"


class DriveNeedsLogin(Exception):
    pass


def login():
    """Mở trình duyệt để chủ đăng nhập Google một lần."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(CRED), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")


def _service():
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    if not TOKEN.exists():
        raise DriveNeedsLogin()
    creds = Credentials.from_authorized_user_file(str(TOKEN))
    if not creds.has_scopes(SCOPES):  # token cũ chỉ có quyền drive.file → đăng nhập lại để lấy quyền mới
        raise DriveNeedsLogin()
    if not creds.valid:
        try:
            creds.refresh(Request())
            TOKEN.write_text(creds.to_json(), encoding="utf-8")
        except RefreshError:
            raise DriveNeedsLogin()
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload(path: Path) -> str:
    """Tải file lên thư mục BotHocTap trên Drive, trả về đường link xem."""
    from googleapiclient.http import MediaFileUpload
    import os
    svc = _service()
    fid = os.environ.get("DRIVE_FOLDER_ID", "").strip()  # thư mục đích có sẵn (id trong link .../folders/<id>)
    if not fid:
        q = f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        folders = svc.files().list(q=q, fields="files(id)").execute().get("files", [])
        if folders:
            fid = folders[0]["id"]
        else:
            fid = svc.files().create(body={"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
                                     fields="id").execute()["id"]
    media = MediaFileUpload(str(path), resumable=True, chunksize=8 * 1024 * 1024)
    req = svc.files().create(body={"name": path.name, "parents": [fid]}, media_body=media,
                             fields="id,webViewLink", supportsAllDrives=True)
    resp = None
    retries = 0
    while resp is None:
        try:
            _, resp = req.next_chunk()
        except Exception:
            retries += 1
            if retries > 20:
                raise
            import time
            time.sleep(5)  # mạng/VPN rớt: thử tiếp từ đoạn đang dở
    return resp["webViewLink"]


if __name__ == "__main__":
    if not CRED.exists():
        print("Chưa có credentials.json. Làm theo HUONG_DAN_DRIVE.md trước.")
        sys.exit(1)
    login()
    print("Đã đăng nhập Google Drive xong. Có thể đóng cửa sổ này.")
