# BugPilot AI — Automated Bug Investigator & PR Reviewer

BugPilot AI — мультиагентная система для автоматического анализа ошибок, генерации исправлений и проверки программного кода с использованием LLM и LangGraph.

## Технологии

- Python, FastAPI
- LangGraph
- Groq API (GPT-OSS-120B)
- GitHub API
- SQLite
- Docker & Docker Compose
- HTML, CSS, JavaScript
- Telegram Bot API

## 1. Установка проекта

Для запуска необходимо установить Git и Docker Desktop.

Склонируйте оба репозитория в одну папку:

```bash
git clone https://github.com/asel6320/bugpilot-ai-agent.git
git clone https://github.com/asel6320/bugpilot-buggy-app.git

cd bugpilot-ai-agent
```

## 2. Настройка переменных окружения

Создайте файл `.env`:

```bash
cp .env.example .env
```

Откройте файл `.env` и заполните необходимые параметры:

```env
APP_ID=buggy-app-001
TARGET_REPO=asel6320/bugpilot-buggy-app

LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b

GITHUB_TOKEN=
GITHUB_WEBHOOK_SECRET=
APPROVAL_TOKEN=

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

DB_PATH=/data/runs.db
```

- `GROQ_API_KEY` — API-ключ, который можно получить на https://console.groq.com/keys.
- `GITHUB_TOKEN` — токен GitHub для создания Pull Request.
- `APPROVAL_TOKEN` — секретный ключ для подтверждения изменений.
- `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` — необязательные параметры для уведомлений.

Для генерации `APPROVAL_TOKEN`:

```bash
openssl rand -hex 32
```

Для создания Pull Request необходимо иметь права записи в целевой репозиторий. Можно создать собственный fork тестового приложения и указать его в `TARGET_REPO`.

## 3. Запуск проекта

Запустите Docker Desktop и выполните:

```bash
docker compose up -d --build
```

Проверка контейнеров:

```bash
docker compose ps
```

После запуска будут доступны:

| Сервис | Адрес |
|---|---|
| BugPilot AI Dashboard | http://localhost:8000 |
| Buggy Application | http://localhost:8001 |
| Swagger API | http://localhost:8000/docs |

## 4. Как работает система

1. Пользователь запускает ошибку в тестовом приложении.
2. Система получает traceback.
3. Repository Agent загружает исходный код из GitHub.
4. Investigator Agent определяет причину ошибки.
5. Fixer Agent генерирует исправление.
6. Reviewer Agent проверяет предложенный код.
7. Пользователь подтверждает изменения.
8. Система создаёт Pull Request в GitHub.

Взаимодействие агентов реализовано с помощью LangGraph.

## 5. Демонстрация проекта

Откройте http://localhost:8000 и выберите один из сценариев:

- ZeroDivisionError
- KeyError
- IndexError
- ValueError
- AttributeError
- TypeError

После завершения расследования в интерфейсе отображаются причина ошибки, предложенное исправление, изменения кода (diff), этапы работы агентов и время выполнения.

Для создания Pull Request необходимо ввести `APPROVAL_TOKEN`, подтверждение `PUBLISH PR` и одобрить изменения.

Рекомендуется запускать сценарии по одному из-за ограничений Groq API.

## 6. Остановка проекта

```bash
docker compose down
```

Для просмотра логов:

```bash
docker compose logs -f agent
```

## 7. Особенности проекта

- Мультиагентная архитектура.
- Автоматический анализ ошибок и генерация исправлений.
- Повторные попытки при неудачном исправлении.
- Обработка ограничений Groq API.
- Human-in-the-loop.
- Интеграция с GitHub.
- Фоновая обработка расследований.
- Хранение истории в SQLite.
- Веб-интерфейс для мониторинга.





