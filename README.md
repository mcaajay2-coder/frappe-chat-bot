# ⛪ KOINONIA Assistant

**KOINONIA Assistant** is a specialized, role-aware Catholic Diocesan & Parish AI Assistant built natively for the **Frappe Framework**. It provides intelligent querying across sacrament registries, family records, member profiles, and administrative jurisdictions with sub-second hybrid vector search, dynamic visualizations, and multilingual voice recognition (Tamil, Tanglish & English).

---

## 🌟 Key Features

1. **🛡️ Strict Hierarchical Role-Based Jurisdictional Access Control:**
   * **Bishop / Curia / Chancellor / System Manager**: Full access across all parishes in their diocese.
   * **Vicar General / Vicar Forane**: Scoped strictly to their designated vicariates and parishes.
   * **Parish Priest**: Strictly isolated to their assigned parish records.
   * **Parishioner**: Limited to their personal and parish registries.
   * *Zero data leakage across diocesan boundaries enforced in both SQL and Desk list views.*

2. **🧠 Advanced Hybrid RAG Engine (LangGraph + BGE-M3 + Cross-Encoder):**
   * Multi-stage query enhancement, schema routing, semantic few-shot selection, and MariaDB SQL generation.
   * Multi-key Groq LLM rotation with automatic fallback and failover.

3. **🗣️ Multilingual Speech & Contextual Phonetic Cleanser:**
   * Full understanding of **Pure Tamil (தமிழ்)**, **Tanglish**, and **English**.
   * Automatic phonetic speech correction for Catholic terminology (e.g. *Puthu Nanmai*, *Kalyanam*, *Gnanasnanam*, *Vicars*, *Anbiyam*, *Parish*).

4. **📊 Intelligent Visualization & Reporting:**
   * Dynamic, interactive Chart.js charts (Bar, Pie, Donut, Line) generated on-demand.
   * One-click PDF export (`KOINONIA Registry Report`) and Excel/CSV download.
   * Real-time pagination, sorting, and inline search for tabular data.

---

## 📂 Core Custom DocTypes Included

The app comes bundled with 11 custom Catholic Church DocTypes:
* `Diocese` — Diocesan governance and administrative details
* `Vicariate` — Deanery / Vicariates grouping multiple parishes
* `Parish` — Parish directory, patron saint, feast days, priests
* `Family` — Family card register, BCC / Anbiyam associations
* `Member` — Comprehensive parishioner directory and relationships
* `Baptism` — Holy Sacrament of Baptism Registry
* `Communion` — First Holy Communion Registry
* `Confirmation` — Sacrament of Confirmation Registry
* `Marriage` — Holy Matrimony Registry (Banns, witnesses, dispensations)
* `Anointing Of Sick` — Sacrament of the Sick Registry
* `Death` — Christian Burial & Death Register

---

## 🚀 Installation Guide

### Prerequisites
* **Frappe Framework**: Version 15 or 16
* **Python**: 3.10+
* **Database**: MariaDB (standard Frappe DB) + PostgreSQL with `pgvector` extension (for vector search)

---

### Step 1: Clone and Install the App

On your Frappe Bench server:

```bash
# 1. Fetch the app from GitHub into your bench
bench get-app https://github.com/<YOUR_GITHUB_USERNAME>/koinonia_assistant

# 2. Install the app onto your target site
bench --site <your-site-name> install-app koinonia_assistant

# 3. Run migration to sync DocTypes, Roles, and Workspaces
bench --site <your-site-name> migrate
```

---

### Step 2: Configure Site Credentials (`site_config.json`)

Edit your `sites/<your-site-name>/site_config.json` to configure speech recognition and external keys:

```json
{
  "sarvam_api_key": "YOUR_SARVAM_AI_API_KEY",
  "pg_host": "postgres-vector",
  "pg_port": 5432,
  "pg_db": "parish_vectordb",
  "pg_user": "postgres",
  "pg_pass": "password"
}
```

---

### Step 3: Initialize Vector Database

Run the automated vector ingestion script to embed all DocType schemas and few-shot examples into `pgvector`:

```bash
bench --site <your-site-name> execute koinonia_assistant.rag.ingest.setup_database
bench --site <your-site-name> execute koinonia_assistant.rag.ingest.ingest_all_table_schemas
bench --site <your-site-name> execute koinonia_assistant.rag.ingest.ingest_field_schemas
```

---

### Step 4: Access the Assistant

Open your web browser and navigate to:
```
http://<your-host-or-domain>/koinonia-chat
```
or click on the **Koinonia Assistant** workspace directly from the Frappe Desk!

---

## 🔒 Security & Desk Permission Hooks

The app implements real-time Frappe Desk `permission_query_conditions` hooks in `hooks.py`. When diocesan users log into the standard Frappe Desk, all list and form views for `Baptism`, `Communion`, `Confirmation`, `Marriage`, `Death`, `Family`, `Member`, and `Parish` are strictly filtered to their assigned jurisdiction.

---

## 📄 License
MIT License. Developed for the Catholic Diocesan Administration.
