import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

from src.config import (
    TELEGRAM_BOT_TOKEN,
    GOOGLE_SERVICE_ACCOUNT_JSON,
    ADMIN_SPREADSHEET_KEY,
    ADMIN_DATA_SHEET_NAME,
)
from src.services.google_sheets import GoogleSheetsClient
from src.services.subscriptions import SubscriptionManager
from src.utils import safe_strip

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.DEBUG,
)
logger = logging.getLogger(__name__)

# Состояния диалога
ASK_FULL_NAME, ASK_WB_TOKEN = range(2)

# Кнопки
ADD_CABINET_KEY = "Добавить кабинет"
CANCEL_KEY = "Отмена"

# Клавиатуры
KB_START = ReplyKeyboardMarkup([[ADD_CABINET_KEY]], resize_keyboard=True)
KB_CANCEL = ReplyKeyboardMarkup([[CANCEL_KEY]], resize_keyboard=True)

# --------- сервисы ---------
def get_sheets_client() -> GoogleSheetsClient:
    return GoogleSheetsClient(GOOGLE_SERVICE_ACCOUNT_JSON)

def get_sub_manager() -> SubscriptionManager:
    return SubscriptionManager()

# --------- обработчики ---------
async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled error while handling update: %s", context.error)

async def debug_echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        txt = update.message.text if update.message else None
        logger.info(
            "DEBUG_ECHO got update: chat=%s user=%s text=%r",
            update.effective_chat.id if update.effective_chat else None,
            update.effective_user.id if update.effective_user else None,
            txt,
        )
    except Exception:
        logger.exception("DEBUG_ECHO crashed")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просто показываем меню с кнопкой «Добавить кабинет»."""
    await update.message.reply_text(
        "Нажмите «Добавить кабинет», чтобы начать.",
        reply_markup=KB_START,
    )
    return ConversationHandler.END

async def entry_add_cabinet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вход в мастер создания кабинета: спрашиваем ФИО и убираем кнопку «Добавить кабинет»."""
    await update.message.reply_text(
        "Отправьте ФИО клиента.",
        reply_markup=KB_CANCEL,  # переключаем клавиатуру: только «Отмена»
    )
    return ASK_FULL_NAME

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяем мастер и возвращаем начальную клавиатуру."""
    await update.message.reply_text(
        "Окей, прервали настройку.",
        reply_markup=KB_START,
    )
    context.user_data.clear()
    return ConversationHandler.END

async def ask_wb_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_name = safe_strip(update.message.text)
    if full_name == CANCEL_KEY or not full_name:
        return await cancel(update, context)

    context.user_data["full_name"] = full_name

    # убираем любую клавиатуру (никакой "Отмена")
    await update.message.reply_text(
        "Теперь пришлите WB-токен.\n\n"
        "Требования к токену:\n"
        "• категории «Контент» и «Отзывы и вопросы» — <b>на запись</b>.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ASK_WB_TOKEN


async def finalize_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wb_token = safe_strip(update.message.text)
    if wb_token == CANCEL_KEY or not wb_token:
        return await cancel(update, context)

    # Проверка подписки
    user = update.effective_user
    chat = update.effective_chat
    sub_info = get_sub_manager().check_access(user.id)
    if not sub_info.enabled:
        await update.message.reply_text("Подписка не активна.", reply_markup=KB_START)
        context.user_data.clear()
        return ConversationHandler.END

    # Данные пользователя
    full_name: str = context.user_data.get("full_name", "")
    # Фамилия = первое слово ФИО
    surname = (full_name.split()[0] if full_name else "").strip()

    # Создание таблицы
    sheets = get_sheets_client()
    title = f"ИП {surname} — WB Autoresponder"

    await update.message.reply_text("⏳ Таблица создаётся, подождите...")

    # ВАЖНО: ожидается обновлённый метод в google_sheets.py
    # который даёт общий доступ по ссылке «на чтение»
    sh, key, spreadsheet_url = sheets.create_client_spreadsheet(
        title=title,
        anyone_can_read=True,  # публично по ссылке, только чтение
    )

    # Бутстрап листов
    sheets.bootstrap_worksheets(sh)

    # Запись в админку
    admin_row = {
        "client": full_name,
        "type": "Autoresponder",
        "enabled": 1,
        "name": f"IP {surname}",
        "wb_token": wb_token,
        "key_table": key,
        #"chat_": chat.id,
        "size": "",
    }
    try:
        sheets.append_admin_row(ADMIN_SPREADSHEET_KEY, ADMIN_DATA_SHEET_NAME, admin_row)
    except Exception as e:
        logger.exception("Не удалось записать в админку (не критично). %s", e)

    # Готово — возвращаем начальную клавиатуру с «Добавить кабинет»
    await update.message.reply_text(
        f"Готово! Ваша таблица: {spreadsheet_url or sh.url}",
        reply_markup=ReplyKeyboardMarkup([["Добавить кабинет"]], resize_keyboard=True),
    )
    context.user_data.clear()
    return ConversationHandler.END


# --------- сборка приложения ---------
def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            # Кнопка «Добавить кабинет»
            MessageHandler(filters.Regex(f"^{ADD_CABINET_KEY}$"), entry_add_cabinet),
            # На всякий случай разрешим вход в мастер и через команду
            CommandHandler("add", entry_add_cabinet),
        ],
        states={
            ASK_FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_wb_token)],
            ASK_WB_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, finalize_setup)],
        },
        fallbacks=[
            MessageHandler(filters.Regex(f"^{CANCEL_KEY}$"), cancel),
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True,
    )

    # /start просто показывает кнопку «Добавить кабинет»
    app.add_handler(CommandHandler("start", start), group=0)
    app.add_handler(conv, group=0)

    # Логируем всё остальное
    app.add_handler(MessageHandler(filters.ALL, debug_echo), group=1)
    app.add_error_handler(handle_error)

    return app

def main():
    app = build_application()
    logger.info("Bot is up.")
    app.run_polling()

if __name__ == "__main__":
    main()
