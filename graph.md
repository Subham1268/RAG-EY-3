# End-to-End Data Flow

## Offline Pipeline (Document Ingestion)

```text
PDF / PPTX / DOCX / XLSX File
        ↓
parser.py
    → Extracts:
        • TextChunk
        • TableChunk
        • ImageChunk
        ↓
chunker.py
    → Splits content into IndexableChunk
    → ~800 character chunks
    → Adds metadata
        ↓
embedder.py
    → GPT-4o Vision processes images
    → text-embedding-3-large generates embeddings
    → Produces 1536-dimension vectors
        ↓
indexer.py
    → Stores vectors + metadata preview in Pinecone
    → Stores full content + complete metadata in PostgreSQL
````

---

## Online Pipeline (Question Answering)

```text
Consultant asks a question in Microsoft Teams
        ↓
teams/bot.py
    → Sends HTTP POST request to api/main.py
        ↓
api/auth.py
    → Validates Azure AD token
        ↓
api/main.py
    → Retrieves session history
    → Invokes LangGraph workflow
        ↓
agent/graph.py
    → Executes the state machine
```

---

## LangGraph State Machine

```text
query_rewriter_node
    → GPT-4o rewrites user query into 3–4 optimized search queries
        ↓

retriever_node
    → Parallel Pinecone vector search
    → Retrieves ~20 candidate chunks
        ↓

retrieval_grader_node
    → GPT-4o filters irrelevant chunks
    → Keeps ~10 relevant chunks
        ↓

reranker_node
    → Cohere cross-encoder reranks chunks
    → Selects top 5 chunks
        ↓

context_builder_node
    → Fetches full content from PostgreSQL
    → Builds final retrieval context
        ↓

generator_node
    → GPT-4o generates cited answer using retrieved context
        ↓

reflection_grader_node
    → GPT-4o evaluates response quality
        ↓

[If quality is poor AND retry count < 2]
    → retry_prep
    → Loops back to query_rewriter_node

[If quality is good]
    → END
```

---

## Response Delivery

```text
api/main.py
    → Stores assistant response in memory
    → Returns ChatResponse JSON
        ↓
teams/bot.py
    → Builds Adaptive Card
    → Sends formatted response to Microsoft Teams
        ↓
Consultant receives final answer with citations in Teams
```





,
  {
    "file_path": "02_EY_ME_AML_Framework_Assessment_UAE_Bank.pdf",
    "engagement_id": "ME-RC-2023-0089",
    "client": "UAE Commercial Bank",
    "country": "UAE",
    "practice": "Risk & Compliance",
    "year": 2023
  },
  {
    "file_path": "03_EY_ME_Operating_Model_Design_OIA_Oman.docx",
    "engagement_id": "ME-SO-2023-0211",
    "client": "Oman Investment Authority",
    "country": "Oman",
    "practice": "Strategy & Operations",
    "year": 2023
  },
  {
    "file_path": "04_EY_ME_ERM_Framework_BDB_Bahrain.docx",
    "engagement_id": "ME-RC-2023-0134",
    "client": "Bahrain Development Bank",
    "country": "Bahrain",
    "practice": "Risk & Compliance",
    "year": 2023
  },
  {
    "file_path": "05_EY_ME_Supply_Chain_Resilience_KSA_Vision2030.pptx",
    "engagement_id": "ME-SO-2023-0198",
    "client": "KSA Vision 2030 Entity",
    "country": "KSA",
    "practice": "Strategy & Operations",
    "year": 2023
  },
  {
    "file_path": "06_EY_ME_Internal_Controls_Review_Qatar_Real_Estate.pptx",
    "engagement_id": "ME-RC-2023-0221",
    "client": "Qatar Real Estate Developer",
    "country": "Qatar",
    "practice": "Risk & Compliance",
    "year": 2023
  },
  {
    "file_path": "07_EY_ME_KPI_Budget_Tracker_UAE_SmartGov.xlsx",
    "engagement_id": "ME-SO-2023-0177",
    "client": "UAE Smart Government",
    "country": "UAE",
    "practice": "Strategy & Operations",
    "year": 2023
  },
  {
    "file_path": "08_EY_ME_Risk_Register_Kuwait_Finance_House.xlsx",
    "engagement_id": "ME-RC-2023-0156",
    "client": "Kuwait Finance House",
    "country": "Kuwait",
    "practice": "Risk & Compliance",
    "year": 2023
  },
  {
    "file_path": "09_EY_ME_Governance_Board_Effectiveness_KSA_Conglomerate.pdf",
    "engagement_id": "ME-RC-2023-0312",
    "client": "Saudi Diversified Conglomerate",
    "country": "KSA",
    "practice": "Risk & Compliance",
    "year": 2023
  },
  {
    "file_path": "10_EY_ME_Cybersecurity_Resilience_Jordan_Telecom.pdf",
    "engagement_id": "ME-RC-2024-0041",
    "client": "Jordanian Telecom Operator",
    "country": "Jordan",
    "practice": "Risk & Compliance",
    "year": 2024
  },
  {
    "file_path": "11_EY_ME_Digital_Transformation_Charts_KSA_Telecom.pptx",
    "engagement_id": "ME-SO-2023-0147",
    "client": "Saudi Telecom Operator",
    "country": "KSA",
    "practice": "Strategy & Operations",
    "year": 2023
  },
  {
    "file_path": "12_EY_ME_Risk_Compliance_Dashboard_GCC_Q4_2023.pptx",
    "engagement_id": "ME-RC-2023-0400",
    "client": "GCC Portfolio",
    "country": "GCC",
    "practice": "Risk & Compliance",
    "year": 2023
  }