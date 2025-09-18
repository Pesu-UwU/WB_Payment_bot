# quick_test_sheets.py — тест создания таблицы через OAuth token.json (НЕ сервисный аккаунт)
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
import sys
from pathlib import Path

TOKEN_PATH = Path(r"C:\Users\Roman\Documents\WB\wb-autoresponder-bot\token.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",  # чтобы шарить/владеть созданным файлом
]

def load_creds():
    if not TOKEN_PATH.exists():
        print(f"[fail] token.json не найден по пути: {TOKEN_PATH}", file=sys.stderr)
        sys.exit(1)

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # на всякий случай обновим, если токен протух
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds

def main():
    # Для информации — покажем что за файл
    try:
        data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
        print("[info] token.json fields:", ", ".join(sorted(data.keys())))
    except Exception:
        pass

    creds = load_creds()

    # Создаём таблицу через Sheets API
    service = build("sheets", "v4", credentials=creds)
    body = {"properties": {"title": "OAuth create test"}}

    try:
        resp = service.spreadsheets().create(
            body=body, fields="spreadsheetId,spreadsheetUrl"
        ).execute()
        spreadsheet_id = resp["spreadsheetId"]
        spreadsheet_url = resp.get("spreadsheetUrl")
        print("[ok] Created spreadsheet:")
        print("  id :", spreadsheet_id)
        print("  url:", spreadsheet_url)
    except HttpError as e:
        print(f"[error] HttpError {e.status_code}: {e.reason}", file=sys.stderr)
        content = getattr(e, "content", b"") or b""
        print(content.decode("utf-8", errors="ignore"))
        if e.status_code == 403:
            print("\n[hint] Если это снова 403 PERMISSION_DENIED при OAuth:", file=sys.stderr)
            print("  • Проверь, что включены Sheets API и Drive API в ЭТОМ проекте.", file=sys.stderr)
            print("  • Токен получен для того же OAuth-клиента (client_id/secret) проекта.", file=sys.stderr)
            print("  • Тестовый пользователь добавлен на вкладке Test Users у OAuth consent screen.", file=sys.stderr)
        sys.exit(2)

if __name__ == "__main__":
    main()
