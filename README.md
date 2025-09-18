# WB Autoresponder Bot

Телеграм-бот, который:
- принимает ФИО, WB-токен и (опционально) Google email клиента,
- создаёт Google-таблицу с листами **Отзывы** и **Вопросы** и заголовками,
- включает доступ «любой по ссылке — редактор» и (если указан) шарит на email,
- добавляет запись в админ-таблицу (`data`).

## Быстрый старт

1. python -m venv .venv
2. source .venv/bin/activate
3. pip install -r requirements.txt
4. Настроить .env
5. python -m src.main
