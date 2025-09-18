import json
import os
import sys
from pathlib import Path
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

# ⚠️ Минимально нужные скоупы.
# spreadsheets — для работы с Google Sheets
# drive.file — чтобы иметь доступ к файлам, созданным этим приложением (и уметь их шарить позже)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

ROOT = Path(__file__).resolve().parent
CLIENT_SECRET = ROOT / "client_secret.json"
TOKEN_PATH = ROOT / "token.json"


def load_creds() -> Optional[Credentials]:
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        # если рефреш-токен есть — google-api-client сам освежит его при запросе
        return creds
    return None


def save_creds(creds: Credentials) -> None:
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    print(f"[ok] token saved -> {TOKEN_PATH}")


def ensure_oauth() -> Credentials:
    creds = load_creds()
    if creds and creds.valid:
        print("[info] using existing token.json")
        return creds

    if creds and creds.expired and creds.refresh_token:
        print("[info] refreshing token…")
        creds.refresh(Request())  # type: ignore[name-defined]
        save_creds(creds)
        return creds

    if not CLIENT_SECRET.exists():
        print(f"[error] client_secret.json not found at: {CLIENT_SECRET}")
        print("       Put your downloaded OAuth Desktop client file here.")
        sys.exit(2)

    print("[info] launching browser for OAuth…")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    # Откроет браузер и поднимет локальный сервер на 8080 (по умолчанию).
    creds = flow.run_local_server(port=0, prompt="consent")
    save_creds(creds)
    return creds


def create_test_spreadsheet(creds: Credentials):
    service = build("sheets", "v4", credentials=creds)
    body = {"properties": {"title": "WB Tools — OAuth Test"}}
    resp = service.spreadsheets().create(
        body=body, fields="spreadsheetId,spreadsheetUrl"
    ).execute()

    sid = resp["spreadsheetId"]
    url = resp.get("spreadsheetUrl")
    print("\n[ok] Spreadsheet created!")
    print(f"     id : {sid}")
    print(f"     url: {url}\n")
    return sid, url


def main():
    try:
        print(f"[info] cwd={os.getcwd()}")
        print(f"[info] looking for client_secret at: {CLIENT_SECRET}")
        creds = ensure_oauth()
        create_test_spreadsheet(creds)
        print("[done] OAuth flow + Sheets create works. You can now use token.json in your bot.")
    except HttpError as e:
        try:
            data = json.loads(e.content.decode("utf-8"))
        except Exception:
            data = {"error": str(e)}
        print("\n[error] HttpError:", e)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("\n[hints]")
        print("  • Если 403 PERMISSION_DENIED:")
        print("    - Проверь, что OAuth client создан в том же проекте, где включены Sheets/Drive API.")
        print("    - В консоли GCP: APIs & Services → Enabled APIs — там должны быть оба API.")
        print("    - Если тип приложения External — добавь свой Gmail в Test users.")
        print("    - Пройди авторизацию тем аккаунтом, в чей Drive ты хочешь писать.")
        print("  • Если окно авторизации не открывается — проверь брандмауэр/браузер по умолчанию.")
        sys.exit(2)
    except Exception as e:
        print("[error]", repr(e))
        sys.exit(2)


if __name__ == "__main__":
    main()
