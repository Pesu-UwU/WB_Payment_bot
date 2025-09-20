import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from typing import Optional, Tuple, Dict, Any, List


HEADERS = [
    "Артикул продавца",
    "Артикул WB",
    "Дата",
    "Оценка",
    "Отзыв",
    "Ответ",
    "Время ответа",
]

SHEET_FEEDBACKS = "Отзывы"
SHEET_QUESTIONS = "Вопросы"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    # Шаринг больше не используем, drive.file оставим на будущее при необходимости
    "https://www.googleapis.com/auth/drive.file",
]

class GoogleSheetsClient:
    def __init__(self, token_path: str):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        self.creds = creds
        self.gc = gspread.authorize(creds)

    def append_admin_row(self, admin_key: str, admin_sheet_name: str, row_dict: Dict[str, Any]) -> None:
        sh = self.gc.open_by_key(admin_key)
        ws = sh.worksheet(admin_sheet_name)
        header = ws.row_values(1)
        row: List[Any] = [row_dict.get(col, "") for col in header]
        ws.append_row(row, value_input_option="USER_ENTERED")

    def create_client_spreadsheet(
            self,
            title: str,
            anyone_can_read: bool = True,
    ) -> Tuple[gspread.Spreadsheet, str, Optional[str]]:
        # 1) создаём файл через Sheets API
        sheets_service = build("sheets", "v4", credentials=self.creds)
        body = {"properties": {"title": title}}
        resp = sheets_service.spreadsheets().create(
            body=body,
            fields="spreadsheetId,spreadsheetUrl",
        ).execute()

        spreadsheet_id = resp["spreadsheetId"]
        spreadsheet_url = resp.get("spreadsheetUrl")

        # 2) открываем через gspread по ключу
        sh = self.gc.open_by_key(spreadsheet_id)

        # 3) Общий доступ по ссылке ТОЛЬКО НА ЧТЕНИЕ
        if anyone_can_read:
            sh.share(None, perm_type="anyone", role="reader")

        return sh, spreadsheet_id, spreadsheet_url

    def bootstrap_worksheets(self, sh: gspread.Spreadsheet) -> None:
        default_ws = sh.sheet1
        default_ws.update_title(SHEET_FEEDBACKS)
        default_ws.insert_row(HEADERS, 1)
        if not self._worksheet_exists(sh, SHEET_QUESTIONS):
            ws_questions = sh.add_worksheet(title=SHEET_QUESTIONS, rows=1000, cols=26)
            ws_questions.insert_row(HEADERS, 1)
        sh.reorder_worksheets([sh.worksheet(SHEET_FEEDBACKS), sh.worksheet(SHEET_QUESTIONS)])

    def _worksheet_exists(self, sh: gspread.Spreadsheet, title: str) -> bool:
        try:
            sh.worksheet(title)
            return True
        except gspread.WorksheetNotFound:
            return False
