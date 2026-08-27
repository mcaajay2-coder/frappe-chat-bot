# 📊 KOINONIA Assistant — Complete Mermaid Diagrams Collection (v2.0)

---

## 📑 Table of Contents
1. [🌟 Master End-to-End System Workflow Diagram (Ultra-Clear)](#1-master-end-to-end-system-workflow-diagram)
2. [🔄 Detailed Step-by-Step Sequence Flow Diagram](#2-detailed-step-by-step-sequence-flow-diagram)
3. [🧠 LangGraph 7-Node Autonomous State Machine Flow](#3-langgraph-7-node-autonomous-state-machine-flow)
4. [🛡️ Multi-Tier Ecclesiastical RBAC & Security Guard Architecture](#4-multi-tier-ecclesiastical-rbac--security-guard-architecture)
5. [🗄️ Canonical Entity-Relationship Diagram (11 DocTypes ERD)](#5-canonical-entity-relationship-diagram-11-doctypes-erd)
6. [⚡ Groq Multi-Key Rotator & TPM Rate-Limit Bypass Flow](#6-groq-multi-key-rotator--tpm-rate-limit-bypass-flow)
7. [🔍 Hybrid Vector (BGE-M3) + Cross-Encoder Re-Ranking Pipeline](#7-hybrid-vector-bg-m3--cross-encoder-re-ranking-pipeline)
8. [🌐 Multilingual, Phonetic & Multi-Turn Context Resolution Flow](#8-multilingual-phonetic--multi-turn-context-resolution-flow)

---

## 1. Master End-to-End System Workflow Diagram

```mermaid
flowchart TD
    %% Styling Classes
    classDef userLayer fill:#1E293B,stroke:#38BDF8,stroke-width:2px,color:#F8FAFC;
    classDef sttLayer fill:#312E81,stroke:#818CF8,stroke-width:2px,color:#F8FAFC;
    classDef secLayer fill:#881337,stroke:#FB7185,stroke-width:2px,color:#F8FAFC;
    classDef graphNode fill:#064E3B,stroke:#34D399,stroke-width:2px,color:#F8FAFC;
    classDef decision fill:#78350F,stroke:#FBBF24,stroke-width:2px,color:#F8FAFC;
    classDef dbNode fill:#1E1B4B,stroke:#A78BFA,stroke-width:2px,color:#F8FAFC;
    classDef outNode fill:#0F172A,stroke:#38BDF8,stroke-width:2px,color:#F8FAFC;

    %% 1. User & Interaction Layer
    subgraph UI_Layer ["👤 1. USER & CLIENT INTERACTION LAYER"]
        User(["👤 User (Bishop / Priest / Staff / Parishioner)"]):::userLayer
        InputType{"Input Mode?"}:::decision
        VoiceInput["🎙️ Voice Input (Tamil / Tanglish / English Speech)"]:::userLayer
        TextInput["💬 Text Query + Optional Conversation History / Quoted Ref"]:::userLayer
    end

    User --> InputType
    InputType -- Audio Recording --> VoiceInput
    InputType -- Typed Message --> TextInput

    %% 2. Audio & Lexicon Preprocessing Layer
    subgraph Audio_Prep ["🎤 2. AUDIO & PHONETIC NORMALIZATION"]
        Sarvam["📡 Sarvam AI REST API (Tamil/English Speech-to-Text)"]:::sttLayer
        PhoneticClean["🧹 Catholic Lexicon Cleanser (Phonetic typo fixer & Latin/Tamil terms)"]:::sttLayer
    end

    VoiceInput --> Sarvam
    Sarvam --> PhoneticClean
    TextInput --> PhoneticClean

    %% 3. Security & Context Resolution Layer
    subgraph Sec_Layer ["🛡️ 3. ECCLESIASTICAL JURISDICTION & GUARD"]
        FrappeAPI["⚙️ Frappe Backend API: koinonia_assistant.api.process_message()"]:::secLayer
        JurResolver["🔍 User Role & Jurisdiction Resolver (Diocese / Vicariate / Parish ID)"]:::secLayer
        AttackCheck{"Adversarial Threat Check?<br/>(SQLi / DROP / SLEEP / Out-of-Diocese)"}:::decision
        SecBlock["🚫 Immediate Security Rejection (403 Unauthorized / Safe Guard)"]:::secLayer
    end

    PhoneticClean --> FrappeAPI
    FrappeAPI --> JurResolver
    JurResolver --> AttackCheck
    AttackCheck -- "Threat / Foreign Diocese" --> SecBlock
    SecBlock --> ResponseBuilder

    %% 4. LangGraph AI Reasoning Engine
    subgraph RAG_Engine ["🧠 4. LANGGRAPH MULTI-STAGE RAG ENGINE"]
        RouterNode["📍 Node 1: Router Node (Greeting / Sacrament / Directory / Census / Analytics)"]:::graphNode
        RouteCheck{"Query Category?"}:::decision
        DirectGreeting["💬 Direct Greeting / Help Responder"]:::graphNode
        
        EnhancerNode["✨ Node 2: Context Enhancer Node (Multi-Turn Pronoun & Reference Resolution)"]:::graphNode
        RetrieverNode["🔎 Node 3: Schema Retriever Node (Hybrid BGE-M3 + Cross-Encoder Reranker)"]:::graphNode
        SQLGenNode["📝 Node 4: SQL Generator Node (Dynamic Rule Injection + MariaDB Syntax)"]:::graphNode
        
        ValidatorNode["🛡️ Node 5: AST Sandbox Validator (EXPLAIN Query + Safety Checker)"]:::graphNode
        SyntaxCheck{"SQL Valid?"}:::decision
        RewriteNode["🔄 SQL Auto-Rewrite Node (Error Feedback Loop, Max 2 Retries)"]:::graphNode
        
        SQLExecNode["⚡ Node 6: MariaDB Execution Node (Safe Read-Only Query Runner)"]:::graphNode
        FormatNode["🎨 Node 7: Response Formatter & Chart Visualizer Node"]:::graphNode
    end

    AttackCheck -- "Authorized Query" --> RouterNode
    RouterNode --> RouteCheck
    RouteCheck -- "Greeting / Help" --> DirectGreeting
    RouteCheck -- "Data / Sacrament Query" --> EnhancerNode

    EnhancerNode --> RetrieverNode
    RetrieverNode --> SQLGenNode
    SQLGenNode --> ValidatorNode
    ValidatorNode --> SyntaxCheck
    SyntaxCheck -- "Syntax/Column Error" --> RewriteNode
    RewriteNode --> ValidatorNode
    SyntaxCheck -- "Passed Sandbox" --> SQLExecNode
    SQLExecNode --> FormatNode

    %% 5. External Services & Storage
    subgraph Data_Services ["💾 5. DATA STORES & INFERENCE INFRASTRUCTURE"]
        GroqRotator["⚡ Groq 7-Key Round Robin Pool (Qwen-27B / OSS-120B)"]:::dbNode
        PgVectorDB[("🗄️ PostgreSQL 16 + pgvector (1024-dim HNSW Schema Embeddings)")]:::dbNode
        MariaDBStore[("🏛️ MariaDB 10.6 Relational Database (11 Catholic DocTypes)")]:::dbNode
    end

    EnhancerNode <--> GroqRotator
    RetrieverNode <--> PgVectorDB
    SQLGenNode <--> GroqRotator
    RewriteNode <--> GroqRotator
    SQLExecNode <--> MariaDBStore

    %% 6. Multimodal Output & Export
    subgraph Out_Layer ["📊 6. MULTIMODAL PRESENTATION & EXPORT"]
        FormatDecision{"Result Data Type?"}:::decision
        CardView["🕊️ Rich Sacramental Certificate Card (Baptism / Marriage / Profile)"]:::outNode
        TableView["📋 Interactive Responsive Markdown Data Table"]:::outNode
        ChartView["📈 Interactive Visual Charts (Bar Chart / Pie Chart / Trend)"]:::outNode
        ExportButtons["📄 1-Click Excel (.xlsx) & Official PDF Exporters"]:::outNode
        ResponseBuilder["💬 Final Unified JSON Response (User Message + Reply + SQL)"]:::outNode
    end

    DirectGreeting --> ResponseBuilder
    FormatNode --> FormatDecision
    FormatDecision -- "Single Sacrament Record" --> CardView
    FormatDecision -- "Multiple Rows (2 to 50+)" --> TableView
    FormatDecision -- "Analytics / Chart Request" --> ChartView

    CardView --> ResponseBuilder
    TableView --> ExportButtons
    ExportButtons --> ResponseBuilder
    ChartView --> ResponseBuilder

    ResponseBuilder --> FinalClient(["🖥️ Displayed in Glassmorphic Web UI & Frappe Desk"]):::userLayer
```

---

## 2. Detailed Step-by-Step Sequence Flow Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User as 👤 User (Bishop/Priest)
    participant UI as 🖥️ Web Chat UI
    participant STT as 🎙️ Sarvam AI STT
    participant API as ⚙️ Frappe API
    participant Graph as 🧠 LangGraph RAG
    participant Groq as ⚡ Groq LLM Pool
    participant PG as 🗄️ pgvector
    participant DB as 🏛️ MariaDB 10.6

    User->>UI: Speaks voice query or types Tamil/Tanglish text
    alt Audio Input
        UI->>STT: Send raw audio blob (WAV/WEBM)
        STT-->>UI: Return transcribed text
    end

    UI->>API: POST /api/method/koinonia_assistant.api.process_message(query, history)
    API->>API: Resolve Jurisdiction: Role=Bishop, Diocese=Trichy
    API->>Graph: Initialize GraphState(query, role, diocese, parish)

    Graph->>Graph: 1. Clean phonetic keywords & detect pronouns
    Graph->>Groq: 2. Enhance query (Multi-turn reference resolution)
    Groq-->>Graph: Return standalone search question

    Graph->>PG: 3. Dense BGE-M3 embedding + pgvector cosine search
    PG-->>Graph: Return Top-5 candidate table schemas & columns
    Graph->>Graph: Re-rank schemas with Cross-Encoder (ms-marco-MiniLM)

    Graph->>Groq: 4. Generate MariaDB SQL with RBAC & 48 Canonical Rules
    Groq-->>Graph: Return SELECT SQL Query

    Graph->>DB: 5. EXPLAIN query in sandbox (Validate syntax & permissions)
    DB-->>Graph: EXPLAIN status OK

    Graph->>DB: 6. Execute validated SELECT query
    DB-->>Graph: Return raw dataset records

    alt Single Sacramental Record
        Graph->>Graph: Format Rich Sacramental Certificate Profile Card
    else Multiple Dataset Rows
        Graph->>Graph: Format Responsive Markdown Table with Pagination
    else Chart Visualization Request
        Graph->>Graph: Format 2-Column Chart JSON & Visualizer
    end

    Graph-->>API: Return final_answer + generated_sql + execution_metrics
    API-->>UI: Return JSON Response
    UI-->>User: Render Rich Card / Table / Chart + 1-Click Excel/PDF buttons
```

---

## 3. LangGraph 7-Node Autonomous State Machine Flow

```mermaid
stateDiagram-v2
    [*] --> RouterNode : User Query Received
    
    state RouterNode {
        [*] --> ClassifyIntent
        ClassifyIntent --> DirectAnswer : Greeting / Help / Out of Scope
        ClassifyIntent --> EnhancePipeline : Database Search Required
    }

    DirectAnswer --> FormatResponseNode : Generate Greeting
    EnhancePipeline --> EnhanceQueryNode

    state EnhanceQueryNode {
        [*] --> CheckPronouns
        CheckPronouns --> MergeHistory : Contains 'அவங்களோட' / 'their' / Quoted text
        CheckPronouns --> StandaloneFix : Independent query
        MergeHistory --> StandardizedQuestion
        StandaloneFix --> StandardizedQuestion
    }

    EnhanceQueryNode --> RetrieveContextNode

    state RetrieveContextNode {
        [*] --> GenerateBGEEmbedding
        GenerateBGEEmbedding --> VectorCosineSearch : pgvector HNSW
        VectorCosineSearch --> CrossEncoderRerank : Top-k candidate schemas
        CrossEncoderRerank --> FilteredFewShots
    }

    RetrieveContextNode --> GenerateSQLNode

    state GenerateSQLNode {
        [*] --> SelectPromptTemplate
        SelectPromptTemplate --> ApplyRBACBoundary : Inject diocese_id / parish_id
        ApplyRBACBoundary --> GroqInference : Multi-Key Round Robin
        GroqInference --> RawSQL
    }

    GenerateSQLNode --> ValidateSQLNode

    state ValidateSQLNode {
        [*] --> RegexSanitizer : Sanitize SELECT columns
        RegexSanitizer --> SafetyCheck : Block DROP/INSERT/SLEEP
        SafetyCheck --> MariaDBSandbox : Execute EXPLAIN SQL
    }

    ValidateSQLNode --> ExecuteSQLNode : Validation Succeeded
    ValidateSQLNode --> RewriteSQLNode : Sandbox Error Detected

    state RewriteSQLNode {
        [*] --> AnalyzeDBError
        AnalyzeDBError --> GroqRewrite : Fix column/table name
        GroqRewrite --> RewrittenSQL
    }

    RewriteSQLNode --> ValidateSQLNode : Re-evaluate (Max 2 Retries)
    RewriteSQLNode --> FormatResponseNode : Retries Exhausted (Graceful Fallback)

    state ExecuteSQLNode {
        [*] --> RunReadOnlyQuery
        RunReadOnlyQuery --> FetchDictRows
    }

    ExecuteSQLNode --> FormatResponseNode

    state FormatResponseNode {
        [*] --> CheckRecordCount
        CheckRecordCount --> RenderSacramentCard : Count == 1 & Sacrament Table
        CheckRecordCount --> RenderTable : Count > 1
        CheckRecordCount --> RenderChart : Chart Flag True
    }

    FormatResponseNode --> [*] : Return Final Output to UI
```

---

## 4. Multi-Tier Ecclesiastical RBAC & Security Guard Architecture

```mermaid
graph TD
    UserRequest["Incoming Request from Authenticated User"]
    
    subgraph Tier_1_Identity ["1. Identity & Role Resolution"]
        ResolveRole["Resolve User from tabUser & User Roles"]
        RoleType{"User Role?"}
    end

    UserRequest --> ResolveRole --> RoleType

    subgraph Tier_2_Boundary ["2. Scope & Boundary Enforcement"]
        BishopScope["🏛️ Bishop / Curia: Full Diocese Scope<br/>WHERE diocese_id = '{user_diocese}'"]
        VicarScope["⛪ Vicar Forane: Vicariate Parishes<br/>WHERE vicariate_id = '{user_vicariate}'"]
        PriestScope["✝️ Parish Priest: Assigned Parish Only<br/>WHERE parish_id = '{user_parish}'"]
        AdminScope["🌐 System Admin: Global Cross-Diocese Access"]
    end

    RoleType -- "Bishop / Chancellor" --> BishopScope
    RoleType -- "Vicar Forane" --> VicarScope
    RoleType -- "Parish Priest / Parishioner" --> PriestScope
    RoleType -- "Administrator" --> AdminScope

    subgraph Tier_3_Guardrails ["3. Real-Time Threat Interception"]
        ForeignCheck{"Target in Authorized Scope?"}
        SQLiCheck{"Contains SQLi / Blind Delays / DDL?"}
        AllowQuery["✅ Authorized Query Execution"]
        Block403["🚫 UNAUTHORIZED_DIOCESE / UNAUTHORIZED_PARISH (403 Refusal)"]
        BlockSQLi["🚫 BLOCKED_SECURITY: Threat Signature Intercepted"]
    end

    BishopScope --> ForeignCheck
    VicarScope --> ForeignCheck
    PriestScope --> ForeignCheck
    AdminScope --> SQLiCheck

    ForeignCheck -- "No (Foreign Diocese/Parish)" --> Block403
    ForeignCheck -- "Yes (Authorized)" --> SQLiCheck

    SQLiCheck -- "Malicious (DROP/SLEEP/UNION)" --> BlockSQLi
    SQLiCheck -- "Clean Query" --> AllowQuery
```

---

## 5. Canonical Entity-Relationship Diagram (11 DocTypes ERD)

```mermaid
erDiagram
    tabDiocese ||--o{ tabVicariate : "contains"
    tabDiocese ||--o{ tabParish : "oversees"
    tabVicariate ||--o{ tabParish : "groups"
    tabParish ||--o{ tabFamily : "registers"
    tabParish ||--o{ tabMember : "shepherds"
    tabParish ||--o{ tabSubStation : "manages"
    
    tabFamily ||--o{ tabMember : "composed_of"
    
    tabParish ||--o{ tabBaptism : "administers"
    tabParish ||--o{ tabCommunion : "administers"
    tabParish ||--o{ tabConfirmation : "administers"
    tabParish ||--o{ tabMarriage : "solemnizes"
    tabParish ||--o{ tabDeath : "records"
    tabParish ||--o{ tabAnointingOfSick : "ministers"

    tabDiocese {
        string name PK "Diocese Code"
        string diocese_name "Diocese Full Name"
        string bishop_name "Bishop / Ordinary"
        date established_date "Erection Date"
        string city "Chancery Location"
        string phone "Contact Phone"
        string email "Chancery Email"
    }

    tabParish {
        string name PK "Parish Code"
        string parish_name "Parish Full Name"
        string diocese_id FK "Diocese"
        string vicariate_id FK "Vicariate"
        string patron_saint "Patron Saint"
        date feast_day "Parish Feast Day"
        string parish_priest "Parish Priest"
        string assistant_priest "Assistant Priest"
    }

    tabFamily {
        string name PK "Family Card Number (FC-XXXX)"
        string family_register_number "Official Family Number"
        string parish_id FK "Parish"
        string diocese_id FK "Diocese"
        string vicariate_id FK "Vicariate"
        string zone_id "Zone Name"
        string parish_bcc_id "BCC Unit Name"
        string economic_status "Economic Classification"
    }

    tabMember {
        string name PK "Member ID"
        string first_name "First Name"
        string middle_name "Middle Name"
        string last_name "Last Name"
        string family_id FK "Family Link"
        string relationship_id "Head / Spouse / Son / Daughter"
        string gender "Male / Female"
        date dob "Date of Birth"
        int age "Calculated Age"
        string blood_group_id "Blood Group"
        string living_status "Alive / Deceased"
        date bapt_date "Baptism Date"
        date fhc_date "First Communion Date"
        date cnf_date "Confirmation Date"
        date mrg_date "Marriage Date"
    }

    tabBaptism {
        string name PK "Baptism Record ID"
        string bapt_register_ref "Canonical Register Ref"
        string first_name "Candidate First Name"
        string last_name "Candidate Last Name"
        date bapt_date "Baptism Date"
        string bapt_place "Place of Baptism"
        string bapt_parish_id FK "Parish"
        string father_name "Father"
        string mother_name "Mother"
        string bapt_god_father "Godfather"
        string bapt_god_mother "Godmother"
        string bapt_minister "Administering Minister"
        string family_card_no "Family Card"
    }

    tabMarriage {
        string name PK "Marriage Record ID"
        string mrg_register_ref "Register Number"
        string bridegroom_name "Groom Full Name"
        string bride_name "Bride Full Name"
        date mrg_date "Marriage Date"
        string mrg_parish_id FK "Parish"
        string mrg_minister "Solemnizing Priest"
        string witness1_name "Witness 1"
        string witness2_name "Witness 2"
    }

    tabDeath {
        string name PK "Death Record ID"
        string first_name "Deceased First Name"
        string last_name "Deceased Last Name"
        date death_date "Date of Death"
        date burial_date "Burial Date"
        string cemetery_code "Cemetery Name"
        string death_cause "Cause of Death"
        string parish_id FK "Parish"
    }
```

---

## 6. Groq Multi-Key Rotator & TPM Rate-Limit Bypass Flow

```mermaid
flowchart TD
    APIRequest["Incoming LLM Inference Request"] --> KeySelector["🔑 Key Selector (Index i = 0..6)"]
    
    subgraph Rotator_Pool ["Groq 7-Key Failover Pool"]
        Key1["Key #1 (Primary)"]
        Key2["Key #2"]
        Key3["Key #3"]
        Key4["Key #4"]
        Key5["Key #5"]
        Key6["Key #6"]
        Key7["Key #7"]
    end

    KeySelector --> Key1
    
    Key1 -- "Success (200 OK)" --> ReturnResponse["Return LLM Completion"]
    Key1 -- "413 / 429 TPM Rate Limit" --> StepSleep1["Backoff Sleep 1.0s"]
    StepSleep1 --> Key2

    Key2 -- "Success (200 OK)" --> ReturnResponse
    Key2 -- "413 / 429 TPM Rate Limit" --> StepSleep2["Backoff Sleep 1.0s"]
    StepSleep2 --> Key3

    Key3 -- "Success (200 OK)" --> ReturnResponse
    Key3 -- "413 / 429 TPM Rate Limit" --> StepSleep3["Backoff Sleep 1.0s"]
    StepSleep3 --> ModelFallback["Model Rotation: Qwen 3.8 -> Qwen 3.6 -> OSS 120B"]
    ModelFallback --> Key4

    Key4 -- "Success" --> ReturnResponse
    Key4 -- "Rate Limit" --> Key5
    Key5 -- "Rate Limit" --> Key6
    Key6 -- "Rate Limit" --> Key7
    Key7 -- "Success" --> ReturnResponse
    Key7 -- "All Keys Exhausted" --> FallbackRescue["Graceful Degradation / Local Cache Response"]
```

---

## 7. Hybrid Vector (BGE-M3) + Cross-Encoder Re-Ranking Pipeline

```mermaid
flowchart LR
    subgraph Query_Input ["User Query Input"]
        RawQ["'2024-ல ஞானஸ்நானம் எடுத்தவர்கள் பட்டியல்'"]
    end

    subgraph Embedding_Engine ["BGE-M3 Dual Embedding"]
        DenseEmbed["Dense Vector (1024-dim)"]
        SparseLexical["Lexical Sparse Token Weights"]
    end

    RawQ --> DenseEmbed
    RawQ --> SparseLexical

    subgraph Vector_DB ["PostgreSQL 16 + pgvector"]
        HNSWIndex["HNSW Cosine Index Search<br/>(Top-15 DocType & Column Candidates)"]
    end

    DenseEmbed --> HNSWIndex
    SparseLexical --> HNSWIndex

    subgraph Cross_Encoder ["Cross-Encoder Re-Ranker"]
        MiniLM["ms-marco-MiniLM-L-6-v2<br/>Deep Cross-Attention Scoring"]
        TopK["Top-5 Most Relevant Schemas & Exact Columns Selected"]
    end

    HNSWIndex --> MiniLM --> TopK
    TopK --> PromptContext["Injected into SQL Generation Context (sub-1,500 tokens)"]
```

---

## 8. Multilingual, Phonetic & Multi-Turn Context Resolution Flow

```mermaid
flowchart TD
    UserQuery["User Input: 'அவங்களோட பங்கு பெயர் அப்புறம் குடும்ப அட்டை குடு'"]
    
    subgraph Stage_1_Phonetic ["Stage 1: Phonetic & Lexicon Cleansing"]
        TamilTerms["Clean Tamil Terms: 'பங்கு பெயர்' -> parish name, 'குடும்ப அட்டை' -> family_card_no"]
    end

    UserQuery --> TamilTerms

    subgraph Stage_2_Context ["Stage 2: Conversational Multi-Turn Extension"]
        CheckHistory{"Prior History Present & Pronoun Found?"}
        HistoryBuffer["Prior Turn: '1995 ஆம் ஆண்டு कितने பேர் புது நன்மை எடுத்தார்கள் -> Total: 75'"]
        MergeContext["Merge Context: 'List the 75 persons who received First Holy Communion in 1995 with their parish name and family card number'"]
    end

    TamilTerms --> CheckHistory
    CheckHistory -- "Pronoun 'அவங்களோட' Found" --> HistoryBuffer --> MergeContext

    subgraph Stage_3_Execution ["Stage 3: Grounded Query Execution"]
        GeneratedSQL["SELECT first_name, last_name, fhc_parish_id AS parish_name, family_card_no FROM tabCommunion WHERE diocese_id = 'Trichy' AND YEAR(fhc_date) = 1995 LIMIT 75"]
    end

    MergeContext --> GeneratedSQL

    subgraph Stage_4_Output ["Stage 4: Responsive Markdown Table"]
        TableOutput["| Full Name | Parish Name | Family Card No |<br/>| Joseph Devadoss F. | Christ the King Parish | FC-80143 |<br/>... 75 candidates"]
    end

    GeneratedSQL --> TableOutput
```
