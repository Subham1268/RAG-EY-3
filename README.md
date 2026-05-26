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
| `--path` not applied to manifest files | Fixed path joining in `ingest.py` |