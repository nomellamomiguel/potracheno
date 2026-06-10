import os

# Тестам, импортирующим слой БД, нужен BOT_TOKEN на этапе импорта config.
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DB_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ADMIN_CHAT_ID", "")
