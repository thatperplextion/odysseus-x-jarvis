# Odysseus Analysis

## Summary
Odysseus is a self-hosted AI workspace built around a single FastAPI application with a large static web UI and a modular route/service layer. It supports chat, research, memory, documents, email, calendar, notes, files, model management, MCP tools, and local model-serving workflows.

## Project Architecture
- One Python backend process acts as the application host and route orchestrator.
- Most behavior is organized into route modules under `routes/` and service modules under `src/` and `services/`.
- Runtime state lives under `data/` and is persisted as JSON, SQLite, and cache directories.
- The frontend is served directly from `static/` as HTML, CSS, and ES modules.
- Docker is the primary deployment path, with native Python and platform-specific launchers also supported.

## Backend Framework
- Framework: FastAPI
- Server: Uvicorn
- Language: Python
- Lifecycle: `app.py` builds the app, loads `.env`, initializes managers, mounts routers, and starts background tasks during lifespan startup.
- Windows support: `app.py` forces the Proactor event loop policy so subprocess-backed features work reliably.

## Frontend Framework
- There is no dedicated frontend framework such as React, Vue, or Svelte.
- The UI is a custom static application made of HTML, CSS, and vanilla JavaScript ES modules.
- Main entry files live in `static/index.html`, `static/app.js`, and the `static/js/` tree.
- The frontend is route-driven and uses a single-page shell pattern with modal/tool panels.

## Database
- Primary application database: SQLite by default.
- ORM: SQLAlchemy
- Default database path: `data/app.db`
- The code also persists operational data in JSON files under `data/`.
- ChromaDB is used as the vector store for RAG, memory, and tool indexing.

## Configuration Files
- `.env.example` documents runtime settings and defaults.
- `pyproject.toml` contains pytest configuration.
- `requirements.txt` and `requirements-optional.txt` define core and optional Python dependencies.
- `docker-compose.yml` defines the base container stack.
- `docker-compose.gpu-amd.yml` and `docker-compose.gpu-nvidia.yml` provide GPU variants.
- `docker/entrypoint.sh` handles container startup and permissions.
- `setup.py` bootstraps first-run directories, database tables, and initial admin credentials.

## Startup Process
1. `docker compose up -d --build` builds and starts the stack.
2. The container entrypoint runs `setup.py` and then launches `uvicorn app:app`.
3. `app.py` loads environment variables, registers static MIME types, configures auth and CORS, initializes managers, mounts routes, and starts lifespan tasks.
4. On native Windows, `launcher.py` provides a portable launcher that starts the server, opens the browser, and manages the tray icon.

## Model Providers
- Primary runtime pattern: OpenAI-compatible chat and embedding endpoints.
- Local provider support: Ollama is the default local path and is wired through `LLM_HOST`, `OLLAMA_BASE_URL`, and related discovery logic.
- Documented/provider-adjacent options include OpenAI, Anthropic, Google/Gemini, LM Studio, vLLM, llama.cpp, SGLang, and OpenRouter-style endpoints where supported by the app's model routing.
- Embeddings use either an HTTP embedding endpoint or a local FastEmbed fallback.
- Search providers include SearXNG and optional external search APIs such as Brave, Tavily, Serper, and Google PSE.

## Extension Points
- `routes/` contains the main HTTP feature surfaces.
- `src/` contains orchestration, tool wiring, constants, managers, and shared runtime logic.
- `services/` contains pluggable service adapters like TTS/STT.
- `mcp_servers/` contains standalone MCP server entrypoints.
- `integrations/` contains external integration packages and skill bundles.
- `companion/` provides the LAN pairing bridge.
- `static/js/` is the main frontend extension surface for UI features.

## Folder Structure
- `app.py` - main FastAPI application and route registration.
- `launcher.py` - portable Windows launcher.
- `core/` - database, auth, middleware, constants compatibility, and shared domain models.
- `src/` - runtime constants, initialization, AI orchestration, task scheduling, MCP, background jobs, and helpers.
- `routes/` - HTTP route modules.
- `services/` - optional service implementations.
- `mcp_servers/` - MCP server processes.
- `static/` - browser UI, assets, scripts, styles, and vendored libraries.
- `docs/` - documentation.
- `data/` - runtime state, caches, user content, and SQLite data.
- `docker/` - container entrypoint and overlay files.
- `companion/` - pairing bridge.
- `integrations/` - integration packages and skill assets.

## Where Custom Integrations Should Live
- JARVIS-specific files should live outside Odysseus internals, under the top-level `JARVIS/` workspace.
- Use `JARVIS/Prompts/` for reusable prompt templates.
- Use `JARVIS/Knowledge/` for personal knowledge collections and domain-specific notes.
- Use `JARVIS/Config/` for JARVIS-only settings.
- Use `JARVIS/Scripts/` for orchestration scripts and helpers.
- Use existing Odysseus extension surfaces only when the integration must become part of the framework, such as `mcp_servers/`, `services/`, or `companion/`.

## Areas That Should Not Be Modified Directly
Treat these as framework-owned surfaces unless a change is intentionally part of Odysseus itself:
- `app.py`
- `launcher.py`
- `core/`
- `src/`
- `routes/`
- `static/`
- `services/`
- `mcp_servers/`
- `docker/`
- `Dockerfile`
- `docker-compose*.yml`
- `setup.py`
- `requirements*.txt`
- `pyproject.toml`

## Notes For Day 1
- The safest Day 1 approach is to keep JARVIS documentation, prompts, and supporting scripts separate from the Odysseus application code.
- The framework already has rich integration seams, so future JARVIS automation should connect through documented boundaries rather than directly rewriting core modules.