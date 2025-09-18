# src/services/google_sheets.py
import logging

import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from typing import Optional, Tuple, Dict, Any, List
from gspread.exceptions import APIError


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
    # нужен для шаринга/доступа к созданным файлам
    "https://www.googleapis.com/auth/drive.file",
]

class GoogleSheetsClient:
    def __init__(self, token_path: str):
        # Загружаем пользовательский OAuth-токен
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        # Обновим при необходимости (на будущее)
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
            share_email: Optional[str] = None,
            anyone_can_edit: bool = True,
    ) -> Tuple[gspread.Spreadsheet, str, Optional[str]]:
        # 1) создаём файл через Sheets API (не Drive)
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

        # 3) общий доступ по ссылке (редактор), если нужно
        if anyone_can_edit:
            try:
                sh.share(None, perm_type="anyone", role="writer")
            except APIError as e:
                # не критично — логика бота не ломается
                logging.getLogger(__name__).warning("Cannot set anyone-can-edit: %s", e)

        # 4) персональный доступ по e-mail
        if share_email:
            try:
                # сначала тихо (без письма)
                sh.share(share_email, perm_type="user", role="writer", notify=False)
            except APIError as e:
                text = str(e)
                # кейс: у адреса нет Google-аккаунта → нужно notify=True
                if ("Notify people" in text) or ("no Google account" in text):
                    sh.share(share_email, perm_type="user", role="writer", notify=True)
                # кейс: адрес просто мусорный/неприменим к типу разрешения
                elif ("invalid or not applicable" in text) or ("Invalid" in text):
                    raise ValueError("invalid-email")
                else:
                    raise

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
