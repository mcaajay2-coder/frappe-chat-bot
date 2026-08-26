# 📊 KOINONIA Assistant — Complete Mermaid Diagrams Collection

---

## 📑 Table of Contents
1. [Diagram 1: High-Level End-to-End System Architecture](#1-high-level-end-to-end-system-architecture)
2. [Diagram 2: 6-Tier Layered Architecture Model](#2-6-tier-layered-architecture-model)
3. [Diagram 3: LangGraph 7-Node State Machine Pipeline](#3-langgraph-7-node-state-machine-pipeline)
4. [Diagram 4: End-to-End Voice & Text Query Sequence](#4-end-to-end-voice--text-query-sequence)
5. [Diagram 5: Ecclesiastical Jurisdictional Access & Security Guard](#5-ecclesiastical-jurisdictional-access--security-guard)
6. [Diagram 6: Complete Entity-Relationship Diagram (11 DocTypes ERD)](#6-complete-entity-relationship-diagram-11-doctypes-erd)
7. [Diagram 7: Groq Multi-Key Rotator & Rate-Limit Bypass Flow](#7-groq-multi-key-rotator--rate-limit-bypass-flow)
8. [Diagram 8: Docker Microservices Container Network Topology](#8-docker-microservices-container-network-topology)
9. [Diagram 9: Hybrid Vector Search & Cross-Encoder Re-Ranking Pipeline](#9-hybrid-vector-search--cross-encoder-re-ranking-pipeline)
10. [Diagram 10: Multilingual & Phonetic Speech Normalization Flow](#10-multilingual--phonetic-speech-normalization-flow)

---

## 1. High-Level End-to-End System Architecture

```mermaid
graph TD
    User([User: Bishop / Priest / Staff / Parishioner]) -->|Voice / Text Query| UI[Frontend: Web Chat UI / Frappe Desk]
    
    subgraph Frontend_Services [Frontend Processing]
        UI -->|Audio Blob| Sarvam[Sarvam AI Tamil/English STT]
        Sarvam --> TextFilter[Phonetic & Catholic Lexicon Cleanser]
        TextFilter --> API[Frappe API: process_message]
    end

    subgraph Security_Layer [Jurisdiction & Access Control]
        API --> JurResolve[Resolve User Jurisdiction: Diocese / Vicariate / Parish]
        JurResolve --> Guard[Permission Guard]
    end

    subgraph RAG_Pipeline [LangGraph AI Engine]
        Guard --> Router[1. Router Node]
        Router --> Enhancer[2. Query Enhancer Node]
        Enhancer --> VectorSearch[3. BGE-M3 + Cross-Encoder Retrieval]
        VectorSearch --> SQLGen[4. SQL Generation Node]
        SQLGen --> Validator[5. SQL Sandbox Validator]
        Validator --> SQLExec[6. MariaDB Execution Node]
        SQLExec --> Formatter[7. Response Formatter & Chart Generator]
    end

    subgraph External_Integrations [LLM & Databases]
        SQLGen <--> GroqPool[Groq Multi-Key Rotator Pool]
        VectorSearch <--> PgVector[(PostgreSQL + pgvector)]
        SQLExec <--> MariaDB[(Frappe MariaDB Database)]
    end

    Formatter -->|Formatted Response + Charts + Tables| UI
```

---

## 2. 6-Tier Layered Architecture Model

```mermaid
graph TD
    subgraph Layer_1_Presentation [1. Presentation Layer]
        UI[Glassmorphic Web Client /koinonia-chat]
        DeskWS[Frappe Desk Workspaces & Custom Pages]
        AudioRec[Web Audio API Waveform Recorder]
        ExportEng[PDF & Excel Report Generator]
    end

    subgraph Layer_2_Language [2. Speech & Language Processing Layer]
        SarvamSTT[Sarvam AI Voice Transcription Engine]
        PhoneticClean[Catholic Domain Phonetic Normalizer]
        DualLang[Dual-Language Display & Translation Engine]
    end

    subgraph Layer_3_Security [3. Security & Governance Layer]
        JurResolver[Jurisdiction Resolver]
        SQLGuard[Dynamic SQL Filter Injector]
        DeskHooks[Frappe Desk permission_query_conditions]
    end

    subgraph Layer_4_AI_Engine [4. LangGraph RAG Reasoning Pipeline]
        Router[Router Node]
        Enhancer[Query Enhancer Node]
        Retriever[Hybrid Vector + Cross-Encoder Retriever]
        SQLGen[SQL Generator Node]
        Validator[SQL Sandbox Validator]
        SQLExec[MariaDB Execution Engine]
        Formatter[Response & Chart Formatter Node]
    end

    subgraph Layer_5_LLM [5. LLM Orchestration & Failover]
        GroqPool[Groq 7-Key Multi-Key Rotator]
        LLMModels[GPT-OSS-120B / Qwen3.6-27B / GPT-OSS-20B]
    end

    subgraph Layer_6_Persistence [6. Persistence & Storage Layer]
        MariaDB[(MariaDB 11.8 Relational Storage)]
        PgVector[(PostgreSQL 16 + pgvector)]
        RedisCache[(Redis Cache & Queues)]
    end

    Layer_1_Presentation --> Layer_2_Language
    Layer_2_Language --> Layer_3_Security
    Layer_3_Security --> Layer_4_AI_Engine
    Layer_4_AI_Engine <--> Layer_5_LLM
    Layer_4_AI_Engine <--> Layer_6_Persistence
```

---

## 3. LangGraph 7-Node State Machine Pipeline

```mermaid
stateDiagram-v2
    [*] --> RouterNode: Incoming Query
    RouterNode --> GeneralChat: Intent == General Greeting / Help
    RouterNode --> EnhanceQueryNode: Intent == Data / SQL Query
    GeneralChat --> [*]: Direct Response
    
    EnhanceQueryNode --> RetrieveContextNode: Normalized Query & Embedding
    RetrieveContextNode --> GenerateSQLNode: Injected Schema & Few-Shots
    GenerateSQLNode --> ValidateSQLNode: Raw SQL Query
    ValidateSQLNode --> ExecuteSQLNode: Sanitized Safe SQL
    ValidateSQLNode --> ErrorRecovery: Syntax Error / Unsafe SQL
    ErrorRecovery --> GenerateSQLNode: Retry with LLM Feedback (Max 2)
    ExecuteSQLNode --> FormatResponseNode: SQL Result Rows
    FormatResponseNode --> [*]: Rendered UI Response + Chart JSON
```

---

## 4. End-to-End Voice & Text Query Sequence

```mermaid
sequenceDiagram
    autonumber
    actor ChurchOfficial as Church Official (Bishop / Priest)
    participant AudioUI as Web Audio Recorder / Chat UI
    participant SarvamAPI as Sarvam AI STT
    participant PhoneticModule as Phonetic Normalizer
    participant FrappeAPI as Frappe API (/process_message)
    participant Guard as Jurisdiction Guard
    participant LangGraph as LangGraph RAG Engine
    participant LLM as Groq Rotator Pool
    participant MariaDB as MariaDB 11.8 Database
    participant UI as Chat Display UI

    ChurchOfficial->>AudioUI: Speaks / Types Query (e.g. "கடந்த வருடம் புதுப்பணி list")
    AudioUI->>SarvamAPI: Uploads raw audio blob
    SarvamAPI-->>AudioUI: Raw Tamil transcript ("புதுப்பணி எடுத்தவர்கள்")
    AudioUI->>PhoneticModule: Normalizes phonetics ("புதுப்பணி" -> "புது நன்மை")
    AudioUI->>FrappeAPI: Submits query with session token
    FrappeAPI->>Guard: Checks role permissions (Bishop -> Trichy)
    Guard-->>FrappeAPI: Verified scope (Trichy, All Parishes)
    FrappeAPI->>LangGraph: Invokes state machine with context
    LangGraph->>LLM: Generates SQL for tabCommunion
    LLM-->>LangGraph: SELECT first_name, last_name, family_card_no FROM tabCommunion WHERE diocese_id = 'Trichy' AND YEAR(fhc_date) = 2025
    LangGraph->>MariaDB: Runs safe SQL query in sandbox
    MariaDB-->>LangGraph: Returns 306 records
    LangGraph->>LangGraph: Formats response table & generates Chart config
    LangGraph-->>FrappeAPI: Returns final answer, tabular JSON & suggestions
    FrappeAPI-->>UI: Renders response bubble & Chart/PDF export buttons
    UI-->>ChurchOfficial: Visual display + Download options
```

---

## 5. Ecclesiastical Jurisdictional Access & Security Guard

```mermaid
flowchart TD
    UserQuery[Incoming User Request] --> ResolveRole{Resolve User Role & Diocese}
    
    ResolveRole -->|Bishop / Curia / Chancellor| DioScope[Diocese Wide Scope: WHERE diocese_id = 'User Diocese']
    ResolveRole -->|Vicar Forane| VicScope[Vicariate Wide Scope: WHERE vicariate_id = 'User Vicariate']
    ResolveRole -->|Parish Priest / Staff| ParishScope[Parish Isolated Scope: WHERE parish_id = 'User Parish']
    ResolveRole -->|Parishioner| PersonalScope[Personal Scope: WHERE family_card_no = 'User Family']
    
    DioScope --> CheckForeign{Cross-Diocese Leak Attempted?}
    VicScope --> CheckForeign
    ParishScope --> CheckForeign
    PersonalScope --> CheckForeign
    
    CheckForeign -->|Yes| BlockAccess[Return 🔒 Access Restricted Notice]
    CheckForeign -->|No| InjectSQL[Inject Mandatory Top-Level WHERE Filters]
    
    InjectSQL --> ValidateSandbox{Sandbox Syntax & Destructive Check}
    ValidateSandbox -->|Unsafe: DROP/DELETE/ALTER| RejectQuery[Reject: Destructive Command Blocked]
    ValidateSandbox -->|Safe: SELECT| ExecuteQuery[Execute Safe SQL against MariaDB]
```

---

## 6. Complete Entity-Relationship Diagram (11 DocTypes ERD)

```mermaid
erDiagram
    DIOCESE ||--o{ VICARIATE : contains
    VICARIATE ||--o{ PARISH : groups
    PARISH ||--o{ SUB_STATION : oversees
    PARISH ||--o{ FAMILY : registers
    FAMILY ||--o{ MEMBER : includes
    
    PARISH ||--o{ BAPTISM : administers
    PARISH ||--o{ COMMUNION : administers
    PARISH ||--o{ CONFIRMATION : administers
    PARISH ||--o{ MARRIAGE : solemnizes
    PARISH ||--o{ ANOINTING_OF_SICK : administers
    PARISH ||--o{ DEATH : records

    DIOCESE {
        string diocese_name PK
        string diocese_code
        string bishop_name
        string city
        string phone
        string email
    }
    VICARIATE {
        string vicariate_name PK
        string diocese_id FK
        string vicar_forane
    }
    PARISH {
        string parish_name PK
        string diocese_id FK
        string vicariate_id FK
        string parish_priest
        string patron_saint
        date feast_day
    }
    SUB_STATION {
        string sub_station_name PK
        string parish_id FK
    }
    FAMILY {
        string name PK
        string parish_id FK
        string vicariate_id FK
        string diocese_id FK
        string parish_bcc_id
        string family_register_number
        string economic_status
    }
    MEMBER {
        string name PK
        string family_id FK
        string first_name
        string last_name
        string gender
        date dob
        string living_status
        string marital_status_id
        date bapt_date
        date fhc_date
        date cnf_date
        date mrg_date
    }
    BAPTISM {
        string name PK
        string first_name
        string last_name
        date bapt_date
        string bapt_parish_id FK
        string diocese_id FK
        string family_card_no
        string bapt_minister
    }
    COMMUNION {
        string name PK
        string first_name
        string last_name
        date fhc_date
        string fhc_parish_id FK
        string diocese_id FK
        string family_card_no
        string fhc_minister
    }
    CONFIRMATION {
        string name PK
        string first_name
        string last_name
        date cnf_date
        string cnf_parish_id FK
        string diocese_id FK
        string family_card_no
        string cnf_minister
        string sponsor_name
    }
    MARRIAGE {
        string name PK
        string bridegroom_name
        string bridegroom_last_name
        string bride_name
        string bride_last_name
        date mrg_date
        string mrg_parish_id FK
        string diocese_id FK
        string mrg_minister
    }
    ANOINTING_OF_SICK {
        string name PK
        string first_name
        string last_name
        date anointing_date
        string parish_id FK
        string diocese_id FK
        string anointing_minister
    }
    DEATH {
        string name PK
        string first_name
        string last_name
        date death_date
        date burial_date
        string cemetery
        string parish_id FK
        string diocese_id FK
    }
```

---

## 7. Groq Multi-Key Rotator & Rate-Limit Bypass Flow

```mermaid
flowchart TD
    Start([LLM Invocation Request]) --> SelectKey[Select Active Key: current_key_idx]
    SelectKey --> SendReq[Send Prompt to Primary Model: openai/gpt-oss-120b]
    
    SendReq --> CheckStatus{Response Status}
    CheckStatus -->|200 OK| Success([Return LLM Response])
    
    CheckStatus -->|429 Rate Limit / 413 Token Limit| RotateKey[Increment: current_key_idx = (idx + 1) % len(KEYS)]
    RotateKey --> CheckAttempts{Attempts < Total Keys * 2?}
    
    CheckAttempts -->|Yes| SleepBackoff[Exponential Backoff: sleep(0.5s * attempt)]
    SleepBackoff --> FallbackModel{Attempt > 3?}
    FallbackModel -->|Yes| SwitchFast[Switch to Fallback Model: qwen/qwen3.6-27b]
    FallbackModel -->|No| SelectKey
    SwitchFast --> SelectKey
    
    CheckAttempts -->|No| RaiseError[Raise LLM Pool Exhausted Exception]
```

---

## 8. Docker Microservices Container Network Topology

```mermaid
graph LR
    subgraph External_Traffic [External Traffic]
        ClientBrowser[Browser / Mobile Client] -->|Port 8081:8080| Frontend[frontend: NGINX Reverse Proxy]
    end

    subgraph Internal_Network [frappe_network Bridge]
        Frontend --> Backend[backend: Gunicorn App Server]
        Frontend --> WS[websocket: Node SocketIO]
        
        Backend --> DB[(db: MariaDB 11.8)]
        Backend --> PgVec[(postgres-vector: PostgreSQL 16 pgvector)]
        Backend --> RCache[(redis-cache: Redis)]
        Backend --> RQueue[(redis-queue: Redis)]
        
        Configurator[configurator: Site Initializer] -.-> Backend
        CreateSite[create-site: Auto-Migrator & Seeder] -.-> DB
        
        Scheduler[scheduler: Cron Worker] --> Backend
        QueueShort[queue-short: Fast Worker] --> Backend
        QueueLong[queue-long: Batch Worker] --> Backend
    end
```

---

## 9. Hybrid Vector Search & Cross-Encoder Re-Ranking Pipeline

```mermaid
graph TD
    Query[User Query String] --> Embed[BGE-M3 1024-dim Vector Embedding]
    
    subgraph Vector_DB [PostgreSQL pgvector Database]
        Embed --> DenseSearch[1. Dense Cosine Search: ORDER BY embedding <=> query_vector LIMIT 10]
        Query --> SparseSearch[2. Sparse Lexical Search: BM25Okapi Token Matching LIMIT 10]
    end
    
    DenseSearch --> UnionPool[Candidate Deduplication Pool]
    SparseSearch --> UnionPool
    
    UnionPool --> CrossEncoder[3. Cross-Encoder Re-Ranking: ms-marco-MiniLM-L-6-v2]
    CrossEncoder --> TopK[Top 2 Table Schemas & Top 3 Relevant Columns]
    
    TopK --> LLMPrompt[Inject into SQL_GEN_PROMPT Context]
```

---

## 10. Multilingual & Phonetic Speech Normalization Flow

```mermaid
flowchart LR
    VoiceIn[Voice Input: Tamil / Tanglish / English] --> SarvamSTT[Sarvam AI saaras:v2 STT]
    SarvamSTT --> RawTranscript[Raw Acoustic Transcript]
    
    RawTranscript --> Normalizer{Phonetic Normalizer}
    
    Normalizer -->|'புதுப்பணி' / 'Pudupani'| Fix1['புது நன்மை' / First Holy Communion]
    Normalizer -->|'கல்யாணம்' / 'Kalyanam'| Fix2['திருமணம்' / Holy Matrimony]
    Normalizer -->|'ஞானஸ்தானம்'| Fix3['ஞானஸ்நானம்' / Baptism]
    Normalizer -->|'குடும்ப கோடு' / 'Family code'| Fix4[family_card_no / family_id]
    
    Fix1 --> DualOut[Dual Output Dispatcher]
    Fix2 --> DualOut
    Fix3 --> DualOut
    Fix4 --> DualOut
    
    DualOut -->|Display to User| TamilUI[Clean Tamil Script in Chat Window]
    DualOut -->|Send to AI Engine| EnglishSQL[English Context for SQL Generation]
```
