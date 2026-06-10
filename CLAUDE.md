# CLAUDE.md — контекст проекта «Потрачено» (potracheno)

Telegram-бот напоминаний о повторяющихся платежах (подписки, аренда, налоги, страховки,
курсы и т.п.). Бесплатный, self-hosted. Имя для пользователя — **«Потрачено»**, пакет — `potracheno`.

Пользовательский README — [README.md](README.md). Здесь — контекст для разработки.

## Ключевые решения (не менять без причины)
- **Стек:** Python 3.12, **aiogram 3** (long-polling), **SQLAlchemy 2.0 async + aiosqlite**,
  **APScheduler**, **python-dateutil**. Часовые пояса — stdlib `zoneinfo`.
- **Long-polling, не webhook** — проще для self-hosted, не нужен публичный HTTPS.
- **SQLite** один файл (`data/potracheno.db`), том в Docker. Схема — `Base.metadata.create_all`
  в `init_db()` (миграций пока нет; при изменении моделей — пересоздать или добавить Alembic).
- **Нет «основной валюты».** У каждого платежа своя валюта; в `/status` суммы выводятся
  **раздельно по валютам**, без конвертации и внешних FX-API.
- **Суммы — в минорных единицах** (`amount_minor`, INTEGER). Формат — `format_money()` всегда с
  фикс. числом знаков и неразрывными пробелами (` ` тысячи, ` ` перед символом).
- **«Нет ответа на напоминание = платёж в силе»:** игнор НЕ архивирует; ежедневный `roll`
  переносит дату вперёд и продолжает напоминать. Архив — только «Больше не плачу» или конец
  разового платежа.
- **Пустой выбор напоминаний → «за 1 день»** (`add_payment.step_rem_done`).
- **Удаление = архив** (`status=archived`, история цела); «удалить совсем» — отдельное действие.
- **Неочевидные развилки юзерфлоу согласуются с пользователем** (он просил спрашивать).

## Архитектура
- `bot/main.py` — сборка `Dispatcher`, `DBSessionMiddleware`, порядок роутеров, старт
  `setup_scheduler`, `start_polling`. **Порядок роутеров важен:** `commands` → `onboarding` →
  фичи → `fallback_router`. Команды (`/start`, `/cancel`, …) идут первыми, чтобы работать
  даже внутри FSM-мастера; `fallback_router` — последним.
- `bot/middlewares.py::DBSessionMiddleware` — на каждый апдейт открывает `AsyncSession`,
  гарантирует строку `User` (`repo.get_or_create_user`), кладёт `session` и `user` в data,
  коммитит после хендлера (rollback при исключении). Хендлеры берут `session`/`user` из аргументов.
- `bot/db/models.py` — `User`, `Payment`, `ReminderLog`, `Feedback` (+ enum'ы `Freq`,
  `PaymentStatus`, `ReminderStatus`, `FeedbackKind`).
- `bot/db/repo.py` — все запросы (CRUD платежей, выборки для статуса/планировщика, фидбэк).
- `bot/callbacks.py` — типизированные `CallbackData` (фабрики). `bot/keyboards.py` — клавиатуры.
  `bot/states.py` — FSM. `bot/texts.py` — все строки (RU, HTML).
- `bot/services/`:
  - `money.py` — `CURRENCIES`, `parse_amount` (правило: последняя группа 1..exponent цифр после
    `.`/`,` = дробная часть, иначе разделители тысяч), `format_money`.
  - `recurrence.py` — `next_occurrences(...)` / `next_due_for_payment(payment)`. Неделя — через
    `dateutil.rrule`; месяц/квартал/год — собственный цикл с клэмпом дня (`-1` = последний день,
    31→28/29 и т.п.). Квартал = месяц с шагом `3*interval`.
  - `reminders.py` — материализация `ReminderLog`: `set_initial_due_and_reminders` (создание),
    `rematerialize` (правка/настройки), `advance_payment` («оплатил»/прошло → след. дата или
    архив), `snooze_payment`, `roll_payment` (ежедневный перенос). Время: локальное
    `due_date − offset @ notify_time` → UTC (naive). Прошедшие оффсеты не планируются.
  - `scheduler.py` — `AsyncIOScheduler`: `tick` каждые `scheduler_tick_seconds` (=60) шлёт
    `ReminderLog` где `sent_at IS NULL AND scheduled_for<=now`; `roll` раз в сутки (`roll_hour_utc`).
  - `dates.py`, `timezones.py`, `humanize.py` — парс/формат дат, города→tz, человекочитаемые
    описания периодичности/карточек (HTML, `esc()` для пользовательского текста).
- `bot/handlers/` — `commands`, `onboarding`, `add_payment` (мастер; правки периодичности/
  напоминаний переиспользуют его через `edit_id` в FSM-data → `confirm_save` обновляет, а не
  вставляет), `list_payments`, `edit_payment`, `status`, `reminders_cb`, `feedback`, `settings`.

### Надёжность напоминаний
Подход «тик по БД» (не джоб на каждое напоминание): переживает рестарты без персистентного
job-store. Идемпотентность — уникальный индекс `ReminderLog(payment_id, due_date, offset_index)`;
`materialize_occurrence` добавляет только недостающие оффсеты. FSM-хранилище — `MemoryStorage`
(состояние мастера теряется при рестарте — это осознанно; данные платежей в БД).

## Команды разработки
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                      # все тесты
python -m bot.main          # запуск (нужен BOT_TOKEN в .env)
docker compose up -d        # прод-запуск
```
`tests/conftest.py` задаёт `BOT_TOKEN` для импорта `config` в тестах; `tests/test_reminders.py`
поднимает свой in-memory engine. Тесты `money`/`recurrence` — чистые юниты без БД.

## Конвенции
- Все сообщения — **HTML parse mode** (выставлен в `bot/main.py`). Пользовательский ввод в
  разметке экранировать через `humanize.esc()`.
- Новые строки — только в `texts.py`. Новые callback-кнопки — фабрика в `callbacks.py` +
  билдер в `keyboards.py`.
- Деньги — всегда минорные единицы + `format_money`/`parse_amount`. Даты платежей — UTC в БД
  для `scheduled_for`, локальные для отображения.

## Известные ограничения / возможные доработки
- Правка «периодичность» переспрашивает и напоминания (проходим мастер с шага freq).
- «Несколько раз в квартал» сведено к «каждые 3 месяца по одному числу».
- Интерфейс только RU (строки вынесены — i18n добавляется позже).
- Нет Alembic — при изменении схемы пересоздать БД или внедрить миграции.
- `/status` «за год» = сумма всех списаний в ближайшие 365 дней (для недельных это ~52 шт.).
