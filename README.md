# Sovereign AI

Sovereign AI is a locally-hosted, secure Retrieval-Augmented Generation (RAG) platform with robust document processing capabilities and workspace isolation. It is designed to ensure complete data privacy by keeping all databases, document ingestion, and AI model inference strictly within an isolated local network environment, preventing any data from leaking to public cloud APIs.

## Table of Contents

- [Architecture](#architecture)
- [Flow Diagrams](#flow-diagrams)
  - [Document Upload Flow](#document-upload-flow)
  - [RAG Chat Flow](#rag-chat-flow)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Roles & Permissions](#roles--permissions)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Seeded Users](#seeded-users)
- [Model Registry](#model-registry)
- [Build Roadmap](#build-roadmap)
- [Known Issues](#known-issues)

## Architecture

The system enforces strict network isolation. The Backend and PostgreSQL containers run on an internal Docker network with no internet access. The AI Gateway communicates with local Ollama models via a dedicated NGINX proxy.

```mermaid
graph TD
    User([User]) -->|HTTP :80| Nginx[NGINX Reverse Proxy]
    
    subgraph Public Network
        Nginx -->|Route: /| Frontend[Next.js Frontend :3000]
        Nginx -->|Route: /api| Backend[FastAPI Backend :8000]
        OllamaProxy[Ollama NGINX Proxy :11434]
    end

    subgraph Internal Network (No Internet)
        Backend -->|SQL/Vector Queries| Postgres[(PostgreSQL + pgvector :5432)]
        Backend -->|LLM & Embeddings| OllamaProxy
    end

    OllamaProxy -->|Host Routing| OllamaHost[Host Ollama Server]

    subgraph Ollama Models
        OllamaHost --> Llama[llama3.1:8b (General & Document)]
        OllamaHost --> Qwen[qwen2.5-coder:7b (Coding)]
        OllamaHost --> Llava[llava:7b (Vision)]
        OllamaHost --> Nomic[nomic-embed-text (Embedding)]
    end
```

## Flow Diagrams

### Document Upload Flow

```mermaid
sequenceDiagram
    participant User
    participant Backend
    participant DB as PostgreSQL
    participant BackgroundTask as Background Task
    participant Ollama
    
    User->>Backend: POST /api/documents/upload (File)
    Backend->>DB: Create DocumentStatus (status='processing')
    Backend-->>User: Return 200 OK (status='processing')
    
    Note over Backend, BackgroundTask: Async Processing
    Backend->>BackgroundTask: Run _process_document
    BackgroundTask->>BackgroundTask: Extract Text / Run OCR (PyMuPDF, Tesseract, pdfplumber)
    alt Image Upload (diagram_mode)
        BackgroundTask->>Ollama: Extract Visual Description (llava:7b)
    end
    BackgroundTask->>BackgroundTask: Chunk Text
    BackgroundTask->>Ollama: Generate Embeddings (nomic-embed-text)
    BackgroundTask->>DB: Save DocumentChunks with Embeddings
    BackgroundTask->>DB: Update DocumentStatus (status='completed')
    
    User->>Backend: GET /api/documents/{id}/status
    Backend-->>User: Return status='completed'
```

### RAG Chat Flow

```mermaid
sequenceDiagram
    participant User
    participant Backend
    participant AI_Gateway as Router / Gateway
    participant DB as pgvector
    participant Ollama
    
    User->>Backend: POST /api/chat (Message)
    Backend->>Ollama: Generate query embedding
    Ollama-->>Backend: Embedding vector
    Backend->>DB: Vector Search (Similarity + Workspace ACLs)
    DB-->>Backend: Retrieved Chunks
    Backend->>AI_Gateway: Route Task (Keywords + LLM Fallback)
    AI_Gateway-->>Backend: Return task_key (general/coding/vision/document)
    Backend->>Backend: Construct Augmented Prompt with Chunks
    Backend->>Ollama: Generate Response (via Routed Model)
    Ollama-->>Backend: Final Answer
    Backend->>DB: Save Assistant Message to ChatHistory
    Backend-->>User: Return Answer & Sources
```

## Tech Stack

| Component | Technology |
|---|---|
| **Frontend** | React 18, Next.js 14.2.35, Tailwind CSS |
| **Backend** | Python 3.11, FastAPI, Uvicorn, SQLAlchemy |
| **Database** | PostgreSQL, pgvector |
| **AI/LLM** | Ollama, LangGraph, LangChain Core |
| **Document Processing** | PyMuPDF (pymupdf), pdfplumber, pytesseract, pdf2image, python-docx, openpyxl, xlrd, reportlab, python-pptx, opencv-python-headless |
| **Authentication** | Passlib (bcrypt), python-jose (JWT) |

## Features

- **Document Management**: Upload, delete, and view processing status for various document types (PDF, Word, Excel, Images).
- **Intelligent RAG Chat**: Chat interface with context-aware document retrieval, source citations, and OCR-confidence hedging.
- **AI Router**: An AI Gateway that intelligently routes user queries to specialized models (Coding, Vision, General, Document) using keyword heuristics and LLM fallbacks.
- **Agentic Workflows**: Run multi-step agent tools with an explicit approval gate before risky actions.
- **Workspace Isolation**: Documents and chat contexts are strictly siloed by workspaces.
- **Document Access Control**: Fine-grained ACLs restricting document visibility by user and role.
- **Deliverables Generation**: Generate rich output documents (DOCX, XLSX, PDF, PPTX) directly from agent tools.
- **Audit Logging**: Comprehensive action logging for security and compliance.
- **Admin Dashboard**: Manage users, roles, workspaces, and system settings.

<!-- TODO: Missing BUILD_GUIDE.md - unable to cross-reference planned vs. actual features -->

## Roles & Permissions

| Role | Permissions |
|---|---|
| **employee** (default) | `chat`, `documents.read`, `documents.upload`, `agent.run` |
| **engineer** | `chat`, `documents.read`, `documents.upload`, `agent.run`, `documents.manage` |
| **manager** | `chat`, `documents.read`, `documents.upload`, `agent.run`, `audit.view`, `documents.manage`, `actions.approve` |
| **admin** | `chat`, `documents.read`, `documents.upload`, `agent.run`, `users.manage`, `audit.view`, `documents.manage`, `settings.manage`, `actions.approve` |

## Project Structure

```text
.
├── backend
│   ├── app
│   │   ├── agent          # LangGraph agent definitions & tools
│   │   ├── ai_gateway     # AI router, provider connections & model registry
│   │   ├── api            # FastAPI route handlers
│   │   ├── core           # Security, permissions & JWT
│   │   ├── db             # SQLAlchemy models, initialization & migrations
│   │   └── services       # Document parsing, ingestion & RAG retrieval
│   ├── Dockerfile
│   ├── main.py            # FastAPI application entrypoint
│   └── requirements.txt   # Python dependencies
├── docker-compose.yml     # Multi-container orchestration & networking
├── frontend
│   ├── Dockerfile
│   ├── package.json
│   ├── src
│   │   ├── app            # Next.js App Router (pages: admin, chat, documents, etc.)
│   │   └── lib            # API client utilities
│   └── tailwind.config.ts
├── nginx
│   └── nginx.conf         # Main reverse proxy configuration
└── README.md
```

## Getting Started

### Prerequisites
- Docker and Docker Compose
- [Ollama](https://ollama.com) installed and running locally on your host machine.

### 1. Pull Required Models
You must pull the exact models defined in the AI Gateway registry before starting the stack:
```bash
ollama pull llama3.1:8b
ollama pull qwen2.5-coder:7b
ollama pull llava:7b
ollama pull nomic-embed-text
```

### 2. Start the Stack
Start the containers in detached mode:
```bash
docker compose up --build -d
```

### 3. Access the Application
The NGINX reverse proxy exposes the application on port 80.
- **Frontend UI:** [http://localhost](http://localhost)
- **Backend API:** [http://localhost/api/docs](http://localhost/api/docs) (Swagger UI)

## Environment Variables

| Variable | Location | Description |
|---|---|---|
| `DATABASE_URL` | `docker-compose.yml` (backend) | Connection string for PostgreSQL (e.g., `postgresql://user:password@postgres:5432/sovereign_ai`) |
| `OLLAMA_URL` | `docker-compose.yml` (backend) | Internal URL pointing to the Ollama NGINX proxy (`http://ollama-proxy:11434`) |
| `NEXT_PUBLIC_API_URL` | `docker-compose.yml` (frontend) | Base URL for the frontend API client |

<!-- TODO: Check if any other .env files exist that might not be tracked -->

## Seeded Users

The database is automatically seeded upon initialization (`backend/app/db/init_db.py`). You can log in with the following accounts:

| Role | Email | Workspace |
|---|---|---|
| Admin | `admin@sovereign.local` | general |
| Manager | `manager@sovereign.local` | general |
| Engineer | `engineer@sovereign.local` | engineering |
| Employee | `employee@sovereign.local` | general |

Passwords for these accounts are set in `backend/app/db/init_db.py`. Change them before any real use.

## Model Registry

The system routes LLM calls using the registry defined in `backend/app/ai_gateway/registry.py`. The current configuration is:

| Task Key | Target Model | Provider Backend |
|---|---|---|
| `general` | `llama3.1:8b` | ollama |
| `document` | `llama3.1:8b` | ollama |
| `coding` | `qwen2.5-coder:7b` | ollama |
| `vision` | `llava:7b` | ollama |
| `embedding` | `nomic-embed-text` | ollama |

To swap a model, simply update its `name` attribute in `registry.py` and ensure the model is pulled locally via Ollama.

## Build Roadmap

<!-- TODO: The BUILD_GUIDE.md file is missing from the repository. Below is a placeholder for the requested phase-by-phase checklist. Update this section once the roadmap is recovered. -->
- [ ] Phase 1 (Missing)
- [ ] Phase 2 (Missing)
- [ ] Phase 3 (Missing)

## Known Issues

- **RAG Grounding**: The model can occasionally hallucinate figures (e.g., "160.0 lakh") that do not explicitly appear in the document context. A strict grounding verification step (validating numerical outputs against retrieved chunks) has not yet been implemented.
- **Relevance Cutoff**: There is currently no strict similarity threshold cutoff in the vector search. The system may list and cite unrelated sources if the search query does not yield highly relevant chunks.
- **Embedded Images in Text PDFs**: PDFs that contain text layers along with embedded diagram images are not currently sent to the vision model; only fully scanned pages trigger the vision fallback.

## License

[MIT License](LICENSE) (Placeholder)
