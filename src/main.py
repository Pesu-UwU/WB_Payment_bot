import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes
from src.config import TELEGRAM_BOT_TOKEN, GOOGLE_SERVICE_ACCOUNT_JSON, ADMIN_SPREADSHEET_KEY, ADMIN_DATA_SHEET_NAME
from src.services.google_sheets import GoogleSheetsClient
from src.services.subscriptions import SubscriptionManager
from src.utils import extract_surname, make_spreadsheet_title, make_admin_name, safe_strip
import re
#import asyncio

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.DEBUG,   # включаем подробные логи
)
async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled error while handling update: %s", context.error)

logger = logging.getLogger(__name__)

ASK_FULL_NAME, ASK_WB_TOKEN, ASK_GOOGLE_EMAIL_CONFIRM = range(3)
SKIP_KEY = "Пропустить"
CANCEL_KEY = "Отмена"
KB_SKIP_CANCEL = ReplyKeyboardMarkup(
    [[SKIP_KEY, CANCEL_KEY]],
    resize_keyboard=True,
    one_time_keyboard=True,  # добавили
)


EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)

def normalize_email(s: str) -> str:
    return (s or "").strip().lower()

def is_valid_email(s: str) -> bool:
    return bool(EMAIL_RE.match(normalize_email(s)))


async def debug_echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        txt = update.message.text if update.message else None
        logger.info("DEBUG_ECHO got update: chat=%s user=%s text=%r",
                    update.effective_chat.id if update.effective_chat else None,
                    update.effective_user.id if update.effective_user else None,
                    txt)
    except Exception:
        logger.exception("DEBUG_ECHO crashed")


def get_sheets_client() -> GoogleSheetsClient:
    return GoogleSheetsClient(GOOGLE_SERVICE_ACCOUNT_JSON)

def get_sub_manager() -> SubscriptionManager:
    return SubscriptionManager()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправьте ваше ФИО:", reply_markup=ReplyKeyboardMarkup([[CANCEL_KEY]], resize_keyboard=True))
    return ASK_FULL_NAME

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Окей, прервали настройку.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def ask_wb_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_name = safe_strip(update.message.text)
    if full_name == CANCEL_KEY or not full_name:
        return await cancel(update, context)
    context.user_data["full_name"] = full_name
    await update.message.reply_text("Теперь пришлите WB-токен:", reply_markup=ReplyKeyboardMarkup([[CANCEL_KEY]], resize_keyboard=True))
    return ASK_WB_TOKEN

async def ask_google_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("enter ASK_GOOGLE_EMAIL_CONFIRM user_id=%s", update.effective_user.id)
    wb_token = safe_strip(update.message.text)
    if wb_token == CANCEL_KEY or not wb_token:
        return await cancel(update, context)
    context.user_data["wb_token"] = wb_token
    await update.message.reply_text("Укажите ваш Google-аккаунт (или нажмите Пропустить):", reply_markup=KB_SKIP_CANCEL)
    return ASK_GOOGLE_EMAIL_CONFIRM

async def finalize_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text or ""
    google_email = raw_text.strip()
    logger.info("finalize_setup: got text=%r user_id=%s", google_email, update.effective_user.id)

    if google_email.lower() == CANCEL_KEY.lower():
        return await cancel(update, context)
    if google_email.lower() == SKIP_KEY.lower():
        google_email = None

    # --- антидубль: если уже идёт создание — просто отвечаем и выходим
    if context.user_data.get("setup_running"):
        await update.message.reply_text("Уже создаю таблицу… подождите, пожалуйста.")
        return ConversationHandler.END  # или просто return, если хочешь остаться в стейте

    # помечаем, что начали, и сразу прячем клавиатуру
    context.user_data["setup_running"] = True
    try:
        await update.message.reply_text("Создаю таблицу…", reply_markup=ReplyKeyboardRemove())

        user = update.effective_user
        chat = update.effective_chat
        sub_info = get_sub_manager().check_access(user.id)
        if not sub_info.enabled:
            await update.message.reply_text("Подписка не активна.")
            return ConversationHandler.END

        full_name = context.user_data.get("full_name", "")
        wb_token = context.user_data.get("wb_token", "")
        surname = extract_surname(full_name)

        sheets = get_sheets_client()
        title = make_spreadsheet_title(surname)

        sh, key, spreadsheet_url = sheets.create_client_spreadsheet(
            title=title,
            share_email=google_email,
            anyone_can_edit=True,
        )

        sheets.bootstrap_worksheets(sh)

        admin_row = {
            "client": full_name,
            "type": "Autoresponder",
            "enabled": 1,
            # "id_tg": user.id,  # не пишем
            "name": make_admin_name(surname),
            "wb_token": wb_token,
            "key_table": key,
            #"chat_": chat.id,  # тоже
            "size": "",
        }
        try:
            sheets.append_admin_row(ADMIN_SPREADSHEET_KEY, ADMIN_DATA_SHEET_NAME, admin_row)
        except Exception as e:
            logger.exception("Не удалось записать в админку: %s", e)
            # без сообщения пользователю

        await update.message.reply_text(
            f"Готово! Ваша таблица: {spreadsheet_url or sh.url}"
        )
        return ConversationHandler.END

    finally:
        # снимаем замок и чистим состояние
        context.user_data.pop("setup_running", None)
        context.user_data.clear()


def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_wb_token)],
            ASK_WB_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_google_email)],
            ASK_GOOGLE_EMAIL_CONFIRM: [MessageHandler(filters.ALL, finalize_setup)],
        },
        fallbacks=[MessageHandler(filters.Regex(f"^{CANCEL_KEY}$"), cancel),
                   CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv, group=0)
    app.add_handler(MessageHandler(filters.ALL, debug_echo), group=1)
    app.add_error_handler(handle_error)

    return app

def main():
    app = build_application()
    logger.info("Bot is up.")
    app.run_polling()

if __name__ == "__main__":
    main()
