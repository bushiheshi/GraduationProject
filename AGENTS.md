# Repository Guidelines

## Project Structure & Module Organization

This repository combines a FastAPI backend, static student/login pages, a Vue teacher dashboard, and assessment scripts.

- `backend/app/`: core Python application. Routers are in `routes/`, SQLAlchemy models in `models.py`, schemas in `schemas.py`, and shared logic in `crud.py`, `llm_service.py`, `security.py`, and `config.py`.
- `backend/scripts/` and `backend/sql/`: database initialization and schema helpers.
- `frontend/`: login and student browser assets, plus `vite.config.js`.
- `frontend/teacher-src/`: editable Vue 3 teacher dashboard source.
- `frontend/teacher/`: generated teacher build output. Rebuild it instead of editing bundled assets manually.
- `test/`: standalone assessment, retrieval, textbook knowledge-base, and report experiments.

## Build, Test, and Development Commands

- `pip install -r backend/requirements.txt`: install backend dependencies.
- `Copy-Item backend/.env.example backend/.env`: create local configuration for database and model API settings.
- `cd backend; python scripts/init_db.py`: initialize PostgreSQL tables and seed data helpers.
- `cd backend; uvicorn app.main:app --host 0.0.0.0 --port 18080 --reload`: run the API and static frontend.
- `cd frontend; npm install`: install Vue/Vite dependencies.
- `cd frontend; npm run dev:teacher`: run the teacher dashboard dev server; `/api` proxies to `http://127.0.0.1:18080`.
- `cd frontend; npm run build:teacher`: rebuild production teacher assets into `frontend/teacher/`.
- `.\start-hidden.vbs` / `.\stop-project.vbs`: start or stop the local project without visible PowerShell windows.

## Coding Style & Naming Conventions

Use 4-space indentation for Python, `snake_case` for functions and variables, and PascalCase for SQLAlchemy models and Pydantic schemas. Keep route files grouped by domain under `backend/app/routes/`. Frontend code uses ES modules, Vue 3 composition API, semicolons, and 2-space indentation.

## Testing Guidelines

There is no unified pytest or npm test command yet. Run validation scripts directly, for example `python test/assess_answer_credibility.py`. Name new Python tests `test_*.py`, document required database/API/model services near the top of the script, and keep generated reports or vector artifacts separate from source logic.

## Commit & Pull Request Guidelines

Recent history uses both Conventional Commit prefixes and short summaries. Prefer concise imperative messages, for example `feat: add assignment submission polling`. Pull requests should describe backend/frontend impact, list database or `.env` changes, link related issues, and include screenshots for visible UI changes.

## Security & Configuration Tips

Do not commit `backend/.env`, credentials, API keys, logs, virtual environments, or `node_modules`. Add new required settings to `backend/.env.example` without real secrets. Treat `test/` evaluation weights and AI-detection outputs as experimental unless they are backed by documented rubrics or validation data.
