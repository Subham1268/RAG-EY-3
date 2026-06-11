

# UPDATED README STUFF

## EY Middle East — Agentic RAG System
### Multimodal Knowledge Retrieval · FastAPI · LangGraph · Streamlit

---

## ⚡ TL;DR — you never need to run `pip install` locally

All Python dependencies live inside the Docker image.
Your laptop only needs **Docker Desktop** and **Git**.

---

## Prerequisites

| Tool | Install |
|------|---------|
| Docker Desktop | https://www.docker.com/products/docker-desktop/ |
| Git | https://git-scm.com |

No Python. No pip. No virtualenv on your machine.

---

## Architecture

```
User (Streamlit UI / Teams Copilot)
        │
        ▼
  FastAPI Backend  ←→  Azure AD Auth
        │
        ▼
  LangGraph Agent ──── ConversationMemory (sliding window)
        │
   ┌────┴────┐
   ▼         ▼
Query      Retrieval
Rewriter   Grader (self-RAG)
   │         │
   ▼         ▼
Pinecone  PostgreSQL
(vector)  (metadata)
   │
Cohere Rerank v3
   │
Cohere command-r7b Generation
   │
Response + Citations
        │
        ▼
  Streamlit UI  (http://localhost:8501)
  FastAPI Docs  (http://localhost:8000/docs)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Orchestration | LangGraph |
| LLM (Chat) | Cohere `command-r7b-12-2024` |
| Embeddings | Cohere `embed-english-v3.0` (1024-dim) |
| Image Description | GPT-4o Vision (OpenAI) |
| Vector DB | Pinecone (1024-dim, 2 namespaces) |
| Metadata DB | PostgreSQL 16 |
| Reranking | Cohere Rerank v3 |
| Document Parsing | PyMuPDF, pdfplumber, python-pptx, python-docx, openpyxl |
| Backend API | FastAPI |
| UI | Streamlit |
| Teams Integration | Microsoft Bot Framework SDK |
| Auth | Azure AD / Entra ID |
| Observability | LangSmith + Azure Monitor |
| Infrastructure | Docker Compose |

---

## Project Structure

```
ey_rag/
├── api/                        # FastAPI app
│   ├── main.py
│   ├── auth.py
│   ├── routes.py
│   └── schemas.py
├── agent/                      # LangGraph pipeline
│   ├── graph.py
│   ├── nodes.py
│   ├── tools.py
│   ├── prompts.py
│   └── memory.py
├── ingestion/                  # Document processing
│   ├── parser.py
│   ├── chunker.py
│   ├── embedder.py
│   ├── indexer.py
│   ├── colpali_embedder.py
│   ├── colpali_indexer.py
│   └── metadata_extractor.py
├── ui/                         # Streamlit frontend
│   └── streamlit_app.py
├── teams/                      # Microsoft Teams bot (opt-in)
│   ├── bot.py
│   └── cards.py
├── config/
│   └── settings.py
├── scripts/
│   ├── ingest.py
│   ├── init_db.py
│   └── ey_documents_manifest.json
├── docs/                       # Drop your documents here
├── infra/
│   └── docker-compose.yml
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

---

## First-Time Setup

### 1. Clone and configure

```bash
git clone <your-repo-url>
cd ey_rag
cp .env.example .env
```

Open `.env` and fill in your keys:

```env
OPENAI_API_KEY=sk-...                  # GPT-4o Vision only
PINECONE_API_KEY=pcsk_...              # app.pinecone.io
COHERE_API_KEY=...                     # dashboard.cohere.com
DATABASE_URL=postgresql+asyncpg://ey_rag_user:localdev_password@postgres:5432/ey_rag

# Path to your documents on the host machine (defaults to ./docs)
DOCS_PATH=./docs
```

> **Windows users** — use your actual path, e.g.:
> `DOCS_PATH=C:\Data\vs codes\ey_rag\docs`

---

### 2. Build the image (once, ~2–3 min)

```bash
docker compose build
```

Installs all Python packages, system libraries (PyMuPDF, poppler, LibreOffice, PyTorch, etc.) inside the container. Nothing is installed on your machine.

---

### 3. Start the database

```bash
docker compose up -d postgres
```

---

### 4. Initialise the schema

```bash
docker compose run --rm init
```

Expected output:
```
✅ Database initialisation complete.
```

---

### 5. Add your documents

Place `.pdf`, `.pptx`, `.docx`, or `.xlsx` files in the folder set by `DOCS_PATH` (default: `./docs`).

---

### 6. Ingest documents

```bash
docker compose run --rm ingest
```

On Windows PowerShell with a custom path:

```powershell
$env:DOCS_PATH="C:\Data\vs codes\ey_rag\docs"
docker compose run --rm ingest
```

Expected output:
```
📚 Found 3 document(s) to ingest
   ✅ Chunk pipeline: 47 new chunks indexed (0 duplicates skipped)
   ✅ Chunk pipeline: 31 new chunks indexed (0 duplicates skipped)
   ✅ Chunk pipeline: 42 new chunks indexed (0 duplicates skipped)
Total: 120 new chunks indexed  |  0 duplicates skipped
```

Re-ingesting the same files is safe — already-indexed chunks are detected and skipped automatically (no duplicate API calls, no duplicate vectors).

---

### 7. Start the API + UI

```bash
docker compose up -d api streamlit
```

Verify both are running:

```bash
curl http://localhost:8000/health
# → {"status":"healthy","version":"1.0.0"}
```

Then open your browser:

| Service | URL |
|---------|-----|
| Streamlit UI | http://localhost:8501 |
| FastAPI docs | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

---

### 8. Test with a raw API query

**Bash / curl:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the key findings from the AML framework assessment for the UAE bank?", "session_id": "test-001"}'
```

**PowerShell:**
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/chat" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"question": "What are the key risk and compliance findings in the GCC portfolio dashboard for Q4 2023?", "session_id": "test-007"}' `
  -UseBasicParsing | Select-Object -ExpandProperty Content
```

---

## Day-to-Day Commands

| Task | Command |
|------|---------|
| Start everything | `docker compose up -d` |
| Stop everything | `docker compose down` |
| Ingest new docs | `docker compose run --rm ingest` |
| Re-init DB (wipe + recreate) | `docker compose run --rm init` |
| View API logs | `docker compose logs -f api` |
| View Streamlit logs | `docker compose logs -f streamlit` |
| Shell into API container | `docker compose exec api bash` |
| Run any Python script | `docker compose exec api python scripts/my_script.py` |
| Rebuild after code changes | `docker compose build && docker compose up -d` |
| Enable Teams bot | `docker compose --profile teams up -d` |

---

## Services Overview

| Service | Profile | Port | Description |
|---------|---------|------|-------------|
| `postgres` | default | 5432 | PostgreSQL metadata store |
| `api` | default | 8000 | FastAPI RAG agent |
| `streamlit` | default | 8501 | Streamlit chat UI |
| `init` | tools | — | One-shot DB + Pinecone initialisation |
| `ingest` | tools | — | One-shot document ingestion |
| `bot` | teams | 3978 | Microsoft Teams Bot Framework |

`tools` profile services (`init`, `ingest`) never start with a plain `docker compose up` — they must be run explicitly with `docker compose run --rm`.

---

## Deduplication

`ingest.py` checks Postgres before embedding any chunk:

```
Parse → Chunk → Check Postgres → [skip if exists] → Embed → Index Pinecone
```

- Re-running ingest on the same files is **free** — zero API calls for already-indexed chunks.
- Chunk IDs are hashes of `(source_file, kind, page, index)`, not content. If you edit a document and re-ingest it under the same filename, existing chunks will not be updated. Delete the document record from the DB first, then re-ingest.

---

## Why Docker?

The codebase depends on packages requiring compiled C extensions that routinely break on Windows:

| Package | Requires |
|---------|---------|
| PyMuPDF (`fitz`) | `libmupdf` |
| pdfplumber | `poppler` |
| Pillow | image codecs |
| ColPali / byaldi | PyTorch |

Docker handles all of this in an isolated Linux environment. Your `.env` file and documents folder are mounted in — everything else stays inside the container.

---

## Known Issues Fixed

| Issue | Fix |
|-------|-----|
| `langchain-core` version conflict | Pinned to `>=0.2.22,<0.3.0` |
| `opentelemetry-sdk` conflict | Updated to `1.26.0` |
| `camelot-py[cv]` broken `pdftopng` | Switched to `camelot-py` with no extras |
| PostgreSQL multi-statement error | Split `CREATE TABLE` + `CREATE INDEX` into separate `execute` calls |
| Pinecone dimension mismatch | Changed 1536 → 1024 to match Cohere embeddings |
| OpenAI free tier rate limits | Switched embeddings to Cohere, chat to `command-r7b-12-2024` |
| `ranker_node` import error | Renamed to `reranker_node` in `graph.py` |
| `python-jose` missing in Docker | Added to `requirements.txt` |
| DOCX parsing `NoneType` error | Added `or ""` guard to `w:t` text extraction |
| `--path` not applied to manifest | Fixed path joining in `ingest.py` |
| Streamlit → API connection in Docker | Changed `localhost:8000` → `http://api:8000` via `API_URL` env var |

# EY Middle East — Agentic RAG System
### Multimodal Knowledge Retrieval for Microsoft Teams Copilot

---


## Architecture Overview

```
User (Teams Copilot)
        │
        ▼
  FastAPI Backend  ←→  Azure AD Auth
        │
        ▼
  LangGraph Agent ──── ConversationMemory
        │
   ┌────┴────┐
   ▼         ▼
Query      Retrieval
Rewriter   Grader (self-RAG)
   │         │
   ▼         ▼
Pinecone  PostgreSQL
(vector)  (metadata)
   │
Cohere Rerank
   │
Cohere command-r7b Generation
   │
Response + Citations
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Orchestration | LangGraph |
| LLM (Chat) | Cohere command-r7b-12-2024 |
| Embeddings | Cohere embed-english-v3.0 (1024-dim) |
| Image Description | GPT-4o Vision (OpenAI) |
| Vector DB | Pinecone (1024-dim, 2 namespaces) |
| Metadata DB | PostgreSQL 16 |
| Reranking | Cohere Rerank v3 |
| Document Parsing | PyMuPDF, pdfplumber, python-pptx, python-docx, openpyxl |
| Backend API | FastAPI |
| Teams Integration | Microsoft Bot Framework SDK |
| Auth | Azure AD / Entra ID |
| Observability | LangSmith + Azure Monitor |

---

## Project Structure

```
ey_rag/
├── ingestion/
│   ├── parser.py       # Multi-format parser (PDF/PPTX/DOCX/XLSX)
│   ├── chunker.py      # Text chunking with SHA-256 IDs
│   ├── embedder.py     # Cohere embeddings + GPT-4o Vision
│   └── indexer.py      # Pinecone + PostgreSQL dual write
├── agent/
│   ├── graph.py        # LangGraph state machine
│   ├── nodes.py        # Async node implementations
│   ├── tools.py        # Retrieval + rerank + fetch tools
│   ├── memory.py       # Sliding window session memory
│   └── prompts.py      # Versioned prompts
├── api/
│   ├── main.py         # FastAPI entry point
│   ├── routes.py       # /chat /documents /ingest /health
│   ├── schemas.py      # Pydantic models
│   └── auth.py         # Azure AD JWT middleware
├── teams/
│   ├── bot.py          # Bot Framework activity handler
│   └── cards.py        # Adaptive card templates
├── infra/
│   ├── docker-compose.yml
│   └── Dockerfile
├── config/
│   └── settings.py
├── scripts/
│   ├── init_db.py
│   ├── ingest.py
│   └── ey_documents_manifest.json
└── tests/
```

---

## Setup & Run (Step by Step)

### 1. Clone the repo
```bash
git clone <your-repo-url>
cd ey_rag
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up environment variables
```bash
cp .env.example .env
```
Fill in these keys in `.env`:
```env
OPENAI_API_KEY=sk-...               # For GPT-4o Vision only
PINECONE_API_KEY=...                # app.pinecone.io
POSTGRES_PASSWORD=localdev_password # Must match docker-compose.yml
DATABASE_URL=postgresql+asyncpg://ey_rag_user:localdev_password@localhost:5432/ey_rag
COHERE_API_KEY=...                  # dashboard.cohere.com
```

### 4. Start infrastructure (PostgreSQL + API)
```bash
cd infra
docker compose up -d
cd ..
```

### 5. Initialize the database
```bash
python scripts/init_db.py
```
Expected output:
```
✅ Database initialisation complete.
```

### 6. Ingest documents
```bash
python scripts/ingest.py --manifest scripts/ey_documents_manifest.json --path "C:\Data\vs codes\ey_rag\docs"
```
Expected output:
```
✅ Ingested 12 documents → 57+ chunks indexed.
```

### 7. Verify API is running
```bash
curl http://localhost:8000/health
```
Expected: `{"status":"healthy","version":"1.0.0"}`

### 8. Test your first RAG query (PowerShell)
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/chat" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"question": "What are the key findings from the AML framework assessment for the UAE bank?", "session_id": "test-001"}' `
  -UseBasicParsing | Select-Object -ExpandProperty Content



  Invoke-WebRequest -Uri "http://localhost:8000/chat" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"question": "What are the key risk and compliance findings in the GCC portfolio dashboard for Q4 2023?", "session_id": "test-007"}' `
  -UseBasicParsing | Select-Object -ExpandProperty Content

```

---

## Known Fixes Applied

| Issue | Fix |
|-------|-----|
| `langchain-core` version conflict | Pinned to `>=0.2.22,<0.3.0` |
| `opentelemetry-sdk` conflict | Updated to `1.26.0` |
| `camelot-py[cv]` broken `pdftopng` | Switched to `camelot-py` with no extras |
| PostgreSQL multi-statement error | Split `CREATE TABLE` + `CREATE INDEX` into separate execute calls |
| Pinecone dimension mismatch | Changed from 1536 → 1024 to match Cohere embeddings |
| OpenAI free tier rate limits | Switched embeddings to Cohere, chat to `command-r7b-12-2024` |
| `ranker_node` import error | Renamed to `reranker_node` in `graph.py` |
| `python-jose` missing in Docker | Added to `requirements.txt` |
| DOCX parsing `NoneType` error | Added `or ""` guard to `w:t` text extraction |
| `--path` not applied to manifest files | Fixed path joining in `ingest.py` |# EY-RAG




