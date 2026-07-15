# PyAnswer frontend

PyAnswer — локальный интеллектуальный поиск по синтетической русскоязычной базе вопросов и
ответов о Python. Первый этап реализует законченный пользовательский сценарий
«главная → поиск или RAG-ответ → документ» без backend, базы данных, Qdrant и прямого доступа к
Ollama.

## Стек

- React 18, TypeScript strict, Vite;
- React Router и TanStack Query;
- Tailwind CSS, Lucide React, Sonner;
- React Markdown, remark-gfm и react-syntax-highlighter;
- Vitest, Testing Library, ESLint и Prettier.

Требуется Node.js 18+ и npm 9+.

## Запуск

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Vite откроет приложение на http://localhost:5173.

Проверки:

```bash
npm run typecheck
npm run lint
npm run test
npm run build
```

Production bundle создаётся в каталоге dist.

## Mock-режим

По умолчанию VITE_USE_MOCKS=true. Адаптер имитирует задержки, фильтрацию, сортировку,
pagination, сохранение документов, сессию, стадии RAG и потоковую выдачу ответа. В наборе 22
синтетических документа; тексты реальных публикаций не копируются.

Для проверки error state:

```env
VITE_MOCK_FORCE_ERROR=true
```

Также запрос **error** возвращает тестовую ошибку поиска. Запрос вне тематики, например
«квантовая хромодинамика», демонстрирует недостаточный контекст RAG.

Mock-аккаунт:

```text
user@pyanswer.local
Demo123!
```

Сессия содержит только объект демонстрационного пользователя. Access token не создаётся и не
хранится.

## Маршруты

- / — Spotlight-поиск и системная сводка;
- /search — документы и RAG, состояние хранится в query string;
- /documents/:documentId — полная ветка вопроса и ответов;
- /login — демонстрационный вход;
- /403 — недостаточно прав;
- - — 404.

Поддерживаемые параметры /search: q, view, mode, page, tags, min_score, accepted, has_code, sort.

## Структура

```text
src/
  api/          HTTP-клиент, контракт и выбор адаптера
  app/          корневые providers и Error Boundary
  components/   UI и layout-компоненты
  features/     auth, search, rag, documents
  hooks/        общие клавиатурные хуки
  layouts/      workspace
  mocks/        данные и mock API
  pages/        маршрутные страницы
  routes/       таблица маршрутов
  store/        тема
  test/         тестовая настройка
  types/        доменные TypeScript-типы
  utils/        URL, форматирование и служебные функции
```

## API adapter и будущий FastAPI

Все feature-компоненты используют объект api из src/api/index.ts. При VITE_USE_MOCKS=false
выбирается httpApi, который обращается только к VITE_API_BASE_URL. Предусмотрены методы:

- searchDocuments → GET /search;
- askQuestion → POST /ask;
- getDocument → GET /documents/:id;
- login, logout, getCurrentUser → /auth/\*;
- saveDocument, unsaveDocument → /saved/:documentId;
- sendFeedback → POST /feedback.

Чтобы подключить FastAPI:

1. реализовать перечисленные JSON endpoint с типами из src/types;
2. настроить CORS для origin frontend и cookie-сессию при необходимости;
3. установить VITE_USE_MOCKS=false;
4. указать VITE_API_BASE_URL=http://localhost:8000/api;
5. перезапустить Vite или пересобрать production bundle.

Интеграция потокового FastAPI/SSE локализована в httpApi.askQuestion; UI уже принимает чанки и
технические стадии. Ollama должен вызываться только backend-сервисом.

## Переменные окружения

| Переменная            | Значение по умолчанию     | Назначение                          |
| --------------------- | ------------------------- | ----------------------------------- |
| VITE_USE_MOCKS        | true                      | Выбор mock или HTTP adapter         |
| VITE_API_BASE_URL     | http://localhost:8000/api | Базовый URL будущего FastAPI        |
| VITE_MOCK_FORCE_ERROR | false                     | Принудительный error state mock API |

## Docker production build

```bash
docker build -t pyanswer-frontend .
docker run --rm -p 8080:80 pyanswer-frontend
```

Multi-stage образ собирает Vite bundle и обслуживает его через nginx. Конфигурация включает
fallback React Router, immutable cache для assets и healthcheck /healthz.
