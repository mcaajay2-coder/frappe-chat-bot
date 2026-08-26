import os
import re
import time
import json
import psycopg2
import pymysql
import torch
from typing import TypedDict, Any
from dotenv import load_dotenv

# Initialize LangSmith tracing environment BEFORE importing langchain/langgraph
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '.env')
load_dotenv(dotenv_path)

def _init_langsmith():
    key = os.getenv("LANGCHAIN_API_KEY")
    if not key:
        try:
            import frappe
            if hasattr(frappe, "conf") and frappe.conf:
                key = frappe.conf.get("langchain_api_key")
        except Exception:
            pass
    if key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
        os.environ["LANGCHAIN_API_KEY"] = key
        os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "koinonia_assistant")

_init_langsmith()

from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

_cross_encoder = None
def get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        print("[CrossEncoder] Loading model...")
        _cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    return _cross_encoder

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END

MAX_RETRIES = 2

# Initialize Groq multi-key pool
def _get_groq_keys() -> list[str]:
    keys = []
    # 1. Check environment variables
    env_keys = os.getenv("GROQ_API_KEYS") or os.getenv("GROQ_API_KEY")
    if env_keys:
        if "," in env_keys:
            keys.extend([k.strip() for k in env_keys.split(",") if k.strip()])
        else:
            keys.append(env_keys.strip())

    # 2. Check site_config.json
    try:
        import frappe
        if hasattr(frappe, "conf") and frappe.conf:
            conf_keys = frappe.conf.get("groq_api_keys")
            if conf_keys and isinstance(conf_keys, list):
                keys.extend(conf_keys)
            elif conf_keys and isinstance(conf_keys, str):
                keys.extend([k.strip() for k in conf_keys.split(",") if k.strip()])
            
            single_key = frappe.conf.get("groq_api_key")
            if single_key and single_key not in keys:
                keys.append(single_key)
    except Exception:
        pass

    # Unique while preserving order
    seen = set()
    unique_keys = []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            unique_keys.append(k)

    return unique_keys or [os.getenv("GROQ_API_KEY", "")]

GROQ_API_KEYS = _get_groq_keys()
_current_key_idx = 0

def _setup_langsmith():
    key = os.getenv("LANGCHAIN_API_KEY")
    if not key:
        try:
            import frappe
            if hasattr(frappe, "conf") and frappe.conf:
                key = frappe.conf.get("langchain_api_key")
        except Exception:
            pass
    if key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
        os.environ["LANGCHAIN_API_KEY"] = key
        os.environ["LANGCHAIN_PROJECT"] = "koinonia_assistant"

_setup_langsmith()

# pgvector Connection
PG_CONFIG = {
    "host":     os.getenv("PG_HOST",     "postgres-vector"),
    "port":     int(os.getenv("PG_PORT", 5432)),
    "dbname":   os.getenv("PG_DB",      "parish_vectordb"),
    "user":     os.getenv("PG_USER",    "postgres"),
    "password": os.getenv("PG_PASS",    "password"),
}

# Lazy-loaded BGE-M3 Embeddings
_tokenizer = None
_model = None

def get_bge_model():
    global _tokenizer, _model
    from transformers import AutoTokenizer, AutoModel
    if _tokenizer is None or _model is None:
        print("[BGE-M3] Loading model inside rag_engine...")
        _tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")
        _model = AutoModel.from_pretrained("BAAI/bge-m3")
        _model.eval()
    return _tokenizer, _model

def embed_text(text: str) -> list[float]:
    tokenizer, model = get_bge_model()
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        output = model(**inputs)
    return output.last_hidden_state.mean(dim=1).squeeze().tolist()

def invoke_llm_with_rotation(prompt_messages):
    global _current_key_idx
    total_keys = len(GROQ_API_KEYS)
    
    # Format messages to ensure there is always a human/user message for Qwen/OSS models
    formatted_messages = []
    if isinstance(prompt_messages, str):
        formatted_messages = [("human", prompt_messages)]
    elif isinstance(prompt_messages, list):
        has_human = any((m[0] in ["human", "user"] if isinstance(m, tuple) else getattr(m, 'type', '') in ["human", "user"]) for m in prompt_messages)
        if not has_human:
            formatted_messages = []
            for i, m in enumerate(prompt_messages):
                if i == len(prompt_messages) - 1:
                    role = "human"
                    content = m[1] if isinstance(m, tuple) else m.content
                else:
                    role = m[0] if isinstance(m, tuple) else m.type
                    content = m[1] if isinstance(m, tuple) else m.content
                formatted_messages.append((role, content))
        else:
            formatted_messages = prompt_messages
    else:
        formatted_messages = prompt_messages
    
    models_to_try = [
        "openai/gpt-oss-120b",
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-20b",
        "groq/compound",
        "groq/compound-mini"
    ]
    
    for model_name in models_to_try:
        for attempt in range(total_keys):
            idx = (_current_key_idx + attempt) % total_keys
            key = GROQ_API_KEYS[idx]
            try:
                client = ChatGroq(model=model_name, temperature=0, groq_api_key=key)
                resp = client.invoke(formatted_messages)
                _current_key_idx = idx
                if hasattr(resp, 'content') and isinstance(resp.content, str):
                    resp.content = re.sub(r'<think>.*?</think>', '', resp.content, flags=re.DOTALL).strip()
                return resp
            except Exception as e:
                print(f"[Groq Rotator] {model_name} error on key #{idx+1} ({key[:10]}...): {e}. Rotating...")

    raise RuntimeError("All Groq API keys and models exhausted their rate limits.")

# Groq LLM instance for standard fallback chaining
primary_llm = ChatGroq(
    model="qwen/qwen3.6-27b",
    temperature=0,
    groq_api_key=GROQ_API_KEYS[0],
)
fallback_llm = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0,
    groq_api_key=GROQ_API_KEYS[0],
)
llm = primary_llm.with_fallbacks([fallback_llm])

# ─── pgvector Schema and History Retrieval ────────────────────────────────────

def clean_query_keywords(query: str) -> list[str]:
    words = re.findall(r'\b\w+\b', query.lower())
    stopwords = {
        "list", "show", "count", "get", "find", "all", "of", "the", "a", "an", 
        "with", "for", "in", "on", "at", "by", "from", "where", "select", 
        "me", "us", "give", "display", "retrieve", "search", "query", "database",
        "table", "tables", "record", "records", "data", "row", "rows"
    }
    keywords = []
    for w in words:
        base = w[:-1] if w.endswith('s') and len(w) > 3 else w
        if base not in stopwords and len(base) > 2:
            keywords.append(base)
    return keywords

def rerank_tables(query_text: str, candidates: list[tuple[str, str]]) -> list[str]:
    if not candidates:
        return []
    if len(candidates) == 1:
        return [candidates[0][0]]
        
    candidates_list = []
    for tname, ddl in candidates:
        lines = ddl.split("\n")
        concept = ""
        for line in lines[:3]:
            if "Entity/Concept:" in line or "Table Name:" in line:
                concept += " " + line.strip()
        candidates_list.append(f"- `{tname}`: {concept.strip()}")
        
    candidates_str = "\n".join(candidates_list)
    
    prompt = f"""You are a database table selector for the KOINONIA sacrament database.
Given the user query: "{query_text}"
Select the top 1 to 3 most relevant tables from the candidate list below that are required to answer this query.
If a single table is sufficient, return only that table. If the query requires a JOIN, return all required tables.

Candidates:
{candidates_str}

Return the selected table names as a comma-separated list. Do not write any explanation, markdown, or code blocks. Just return the table names, e.g. "tabFamily, tabMember"."""

    try:
        response = invoke_llm_with_rotation([("system", prompt)])
        content = response.content.strip()
        selected = [t.strip().strip("`").strip("'").strip('"') for t in content.split(",")]
        candidate_names = {c[0] for c in candidates}
        final_selection = [s for s in selected if s in candidate_names]
        if final_selection:
            return final_selection
    except Exception as e:
        print(f"[rerank_tables] Error during LLM re-ranking: {e}")
        
    return [c[0] for c in candidates[:2]]

def fetch_relevant_schemas(original_query: str, enhanced_query: str, query_embedding: list[float], k: int = 2) -> str:
    conn = psycopg2.connect(**PG_CONFIG)
    candidates = []
    seen = set()
    combined_query_text = f"{original_query} {enhanced_query}"
    
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT table_name, schema_ddl FROM koinonia_table_schemas;")
            all_tables = cur.fetchall()
            
            docs = []
            doc_to_table = {}
            for tname, ddl in all_tables:
                doc = f"{tname} {ddl}".lower()
                docs.append(doc)
                doc_to_table[doc] = (tname, ddl)
                
            if docs:
                tokenized_docs = [doc.split() for doc in docs]
                bm25 = BM25Okapi(tokenized_docs)
                tokenized_query = combined_query_text.lower().split()
                bm25_scores = bm25.get_scores(tokenized_query)
                
                top_bm25_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:5]
                for idx in top_bm25_indices:
                    tname, ddl = doc_to_table[docs[idx]]
                    if tname not in seen:
                        seen.add(tname)
                        candidates.append((tname, ddl))
            
            cur.execute("""
                SELECT table_name, schema_ddl
                FROM koinonia_table_schemas
                ORDER BY embedding <=> %s::vector
                LIMIT 5;
            """, (query_embedding,))
            for tname, ddl in cur.fetchall():
                if tname not in seen:
                    seen.add(tname)
                    candidates.append((tname, ddl))
                    
        if candidates:
            ce = get_cross_encoder()
            pairs = [[combined_query_text, f"{tname} {ddl}"] for tname, ddl in candidates]
            scores = ce.predict(pairs)
            
            scored_candidates = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
            top_candidates = [cand for score, cand in scored_candidates[:k]]
        else:
            top_candidates = []
            
        selected_table_names = rerank_tables(original_query, top_candidates)
        schema_map = {tname: ddl for tname, ddl in top_candidates}
        final_results = []
        for tname in selected_table_names:
            if tname in schema_map:
                final_results.append((tname, schema_map[tname]))
                
    except Exception as e:
        print("[RAG Context] Error fetching relevant schemas:", e)
        final_results = []
    finally:
        conn.close()
        
    pruned_results = []
    system_cols = ["_user_tags", "_comments", "_assign", "_liked_by", "amended_from", "idx", "docstatus", "creation", "modified", "modified_by", "owner", "custom", "primary key", "key `", "unique key", "constraint", "engine=", "default charset="]
    for tname, ddl in final_results[:2]:
        clean_lines = []
        for line in ddl.split("\n"):
            line_str = line.strip()
            if not line_str or line_str.startswith("--"):
                continue
            if not any(sc in line_str.lower() for sc in system_cols):
                clean_lines.append(line_str)
        pruned_results.append(f"Table `{tname}`:\n" + "\n".join(clean_lines[:8]))
        
    return pruned_results

def fetch_relevant_fields(query_embedding: list[float], combined_query_text: str, k: int = 3) -> list[str]:
    conn = psycopg2.connect(**PG_CONFIG)
    candidates = []
    seen = set()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT table_name, field_name, field_type, field_label, description FROM koinonia_field_schemas;")
            all_fields = cur.fetchall()
            
            docs = []
            doc_to_row = {}
            for row in all_fields:
                doc = f"{row[0]} {row[1]} {row[2]} {row[3]} {row[4]}".lower()
                docs.append(doc)
                doc_to_row[doc] = row
                
            if docs:
                tokenized_docs = [doc.split() for doc in docs]
                bm25 = BM25Okapi(tokenized_docs)
                tokenized_query = combined_query_text.lower().split()
                bm25_scores = bm25.get_scores(tokenized_query)
                
                top_bm25_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:10]
                for idx in top_bm25_indices:
                    row = doc_to_row[docs[idx]]
                    row_str = f"- Table `{row[0]}`, Column `{row[1]}` (Type: {row[2]}, Label: {row[3]}): {row[4]}"
                    if row_str not in seen:
                        seen.add(row_str)
                        candidates.append((row_str, row))
            
            cur.execute("""
                SELECT table_name, field_name, field_type, field_label, description
                FROM koinonia_field_schemas
                ORDER BY embedding <=> %s::vector
                LIMIT 10;
            """, (query_embedding,))
            for row in cur.fetchall():
                row_str = f"- Table `{row[0]}`, Column `{row[1]}` (Type: {row[2]}, Label: {row[3]}): {row[4]}"
                if row_str not in seen:
                    seen.add(row_str)
                    candidates.append((row_str, row))
                    
        if candidates:
            ce = get_cross_encoder()
            pairs = [[combined_query_text, c[0]] for c in candidates]
            scores = ce.predict(pairs)
            scored_candidates = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
            results = [cand[0] for score, cand in scored_candidates[:k]]
        else:
            results = []
            
    except Exception as e:
        print("[RAG Context] Error fetching relevant fields:", e)
        results = []
    finally:
        conn.close()
    return results

def fetch_few_shot_examples(query_embedding: list[float], k: int = 1) -> str:
    lines = [
        "Example Mappings:",
        "  Q: \"Count how many baptisms were conducted in Holy Cross Parish during 2024\"",
        "  SQL: SELECT COUNT(*) FROM tabBaptism WHERE bapt_parish_id = 'Holy Cross Parish' AND YEAR(bapt_date) = 2024",
        "  Q: \"Tell me about Paul Amalraj S.\"",
        "  SQL: SELECT first_name, middle_name, last_name, dob, gender, living_status, parish_id, mobile FROM tabMember WHERE (first_name = 'Paul' AND middle_name = 'Amalraj' AND last_name = 'S.') OR CONCAT_WS(' ', first_name, NULLIF(middle_name, ''), last_name) LIKE '%Paul%Amalraj%'"
    ]
    
    conn = psycopg2.connect(**PG_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT user_question, generated_sql
                FROM koinonia_query_history
                WHERE correctness_flag = 1
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """, (query_embedding, k))
            rows = cur.fetchall()
    except Exception as e:
        print("[History] Error fetching dynamic few-shots:", e)
        rows = []
    finally:
        conn.close()
        
    if rows:
        lines.append("\nDynamic History Examples:")
        for q, s in rows:
            lines.append(f'  Q: "{q}"\n  SQL: {s}')
            
    return "\n".join(lines)

def log_query_history(question: str, sql: str, embedding: list[float]) -> int:
    conn = psycopg2.connect(**PG_CONFIG)
    row_id = -1
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id FROM koinonia_query_history 
                WHERE user_question = %s 
                LIMIT 1;
            """, (question,))
            existing = cur.fetchone()
            if existing:
                return existing[0]

            cur.execute("""
                INSERT INTO koinonia_query_history (user_question, generated_sql, embedding, correctness_flag)
                VALUES (%s, %s, %s::vector, NULL)
                RETURNING id;
            """, (question, sql, embedding))
            row_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        print("[History] Error logging query history:", e)
    finally:
        conn.close()
    return row_id

def update_correctness_flag(query_id: int, is_correct: int):
    if query_id < 0:
        return
    conn = psycopg2.connect(**PG_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE koinonia_query_history SET correctness_flag = %s WHERE id = %s;
            """, (is_correct, query_id))
        conn.commit()
    except Exception as e:
        print("[History] Error updating correctness flag:", e)
    finally:
        conn.close()

# ─── LangGraph State Definition ───────────────────────────────────────────────

class GraphState(TypedDict):
    question:          str
    history:           list[dict[str, str]]
    reference_text:    str
    route:             str
    enhanced_query:    str
    relevant_tables:   list[str]
    relevant_fields:   list[str]
    few_shot_examples: str
    query_embedding:   list
    generated_sql:     str
    llm_explanation:   str
    sql_result:        Any
    error_message:     str
    retry_count:       int
    final_answer:      str
    history_id:        int
    user_role:         str
    user_parish:       str
    user_vicariate:    str
    user_diocese:      str
    user_parishes:     list[str]
    user_member_id:    str
    user_email:        str
    requested_foreign_parish: str
    requested_foreign_diocese: str

# ─── Graph Nodes ──────────────────────────────────────────────────────────────

def router_node(state: GraphState) -> GraphState:
    print("\n[router] Classifying user query...")
    q = state["question"].strip().lower()
    q_stripped = q.strip(".,!?\"' ")

    # Greetings & Identity / Capabilities
    greetings = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening", "thanks", "thank you", "bye", "goodbye", "namaste", "vanakkam"}
    identity_phrases = [
        "how are you", "who are you", "what can you do", "introduce yourself", 
        "tell me about yourself", "tell me about you self", "tell about yourself", 
        "about yourself", "about you", "what are you", "help me", "help", 
        "what is your name", "your features", "what do you do", "capabilities",
        "how to use", "instructions", "guide me", "what is koinonia"
    ]
    if q_stripped in greetings or any(phrase in q for phrase in identity_phrases):
        return {**state, "route": "greeting"}

    # If completely empty or single punctuation
    if not q_stripped or len(q_stripped) < 2:
        return {**state, "route": "unclear"}

    # All user requests, questions, searches, and name lookups route directly to text_to_sql
    return {**state, "route": "text_to_sql"}

def unclear_node(state: GraphState) -> GraphState:
    answer = (
        "🤔 I'm sorry, I didn't quite get that.\n\n"
        "I am the **KOINONIA Assistant**. I can help you search the parish family register and sacrament records. "
        "Try asking me things like:\n"
        "- *'List all families in Lourdu Matha BCC'* or *'How many members are in Zone 1?'*\n"
        "- *'Find the baptism record of Rani Marianathan'* or *'Who was the burial minister for Jessy Lourdusamy?'*\n"
        "- *'Show all confirmations conducted in 2024'*\n\n"
        "Please let me know how I can assist you!"
    )
    return {**state, "final_answer": answer}

def greeting_node(state: GraphState) -> GraphState:
    import frappe
    user_email = state.get("user_email") or frappe.session.user
    user_name = "there"
    user_title = ""

    if user_email and user_email != "Guest":
        user_name = frappe.db.get_value("User", user_email, "first_name") or frappe.db.get_value("User", user_email, "full_name") or "there"
        roles = frappe.get_roles(user_email)
        if "Bishop" in roles or "Bishop Role" in roles:
            user_title = "Bishop"
        elif "Vicar General" in roles or "Vicar" in roles:
            user_title = "Vicar"
        elif "Parish Priest" in roles:
            user_title = "Father"

    salutation = f"Hello {user_title} {user_name}!" if user_title else f"Hello {user_name}!"
    
    answer = (
        f"👋 **{salutation}** I am **KOINONIA Assistant**, your dedicated Catholic Diocesan & Parish Registry Assistant.\n\n"
        "Here is what I can do for you:\n"
        "• 🏛️ **Parish & Vicariate Registries:** Find parishes, clergy assignments, family counts, and diocese-wide demographics.\n"
        "• 🕊️ **Sacramental Records:** Search and verify records for **Baptism, First Holy Communion, Confirmation, Holy Matrimony, Anointing of the Sick, and Christian Burial**.\n"
        "• 👥 **Family & Census Data:** Explore family registers, Basic Christian Communities (BCC), and parishioner directories.\n"
        "• 📊 **Analytics & Visualizations:** Generate line graphs 📈, bar charts 📊, and pie charts 🥧 for parish statistics upon request.\n"
        "• 📄 **Export Reports:** Export formatted **Excel spreadsheets** and **official PDF documents** with complete headers and totals.\n\n"
        "💬 *Just ask your question in plain English or Tanglish (e.g., 'Show total families in each parish' or 'List baptisms in 2024') and I will fetch the records for you!*"
    )
    return {**state, "final_answer": answer}

ENHANCE_QUERY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a smart query context extension assistant for the KOINONIA Parish Assistant app.
The user is asking a question that references a previous question, record, or quoted text.
Your task is to combine the referenced context with the user's new question into a complete, standalone question for a church/sacrament database assistant.

Examples:
- User Question: "Show me the babtizum records about Jose D." | Reference: "List the users who babtized in 2025"
  -> Enhanced: "Show the baptism records of Jose D. who was baptized in 2025"

- User Question: "tell me about Nirmala Fernando G. family details" | Reference: "Found 50 records matching your search: | Full Name | Bapt Date | Bapt Parish I..."
  -> Enhanced: "Tell me about the family details and family members of Nirmala Fernando G."

- User Question: "List them with their parents" | Reference: "List the users who babtized in 2025"
  -> Enhanced: "List the persons baptized in 2025 with their first name, last name, father name, and mother name"

- User Question: "tell me more about this person" | Reference: "Thomas D'Souza"
  -> Enhanced: "Show details for member Thomas D'Souza"

- User Question: "Show me his marriage records" | Reference: "Jose D"
  -> Enhanced: "Show marriage records for Jose D."

- User Question: "Show next 50 records" | Reference: "Show members in St. Joseph's Parish"
  -> Enhanced: "Show next 50 members in St. Joseph's Parish with offset 50"

- User Question: "Next records" | Reference: "Show marriages in 2025"
  -> Enhanced: "Show next 50 marriages in 2025 with offset 50"

CRITICAL RULES:
1. Return ONLY the extended, standalone question string.
2. Do NOT add markdown, explanations, or quotes.
3. Preserve all specific entity names (names, dates, years, sacraments).
4. When the user asks about family details or family members of a person from a search list, do NOT force baptism dates or sacrament table filters into the family question."""),
    ("human", "{reference_context}\nLatest User Question: {question}"),
])

STANDALONE_ENHANCE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an intelligent Catholic Church terminology and translation assistant for the KOINONIA Parish Assistant app.
Your task is to convert Tamil, Tanglish, and English questions with typos/phonetics into a clean, unambiguous standalone English search query for a church/sacrament database.

CATHOLIC TAMIL TERMINOLOGY MAPPINGS:
- "புது நன்மை" / "புதுநன்மை" / "முதல் நற்கருணை" / "நற்கருணை" -> First Holy Communion (tabCommunion)
- "ஞானஸ்நானம்" / "திருமுழுக்கு" / "மாமோதீசா" -> Baptism (tabBaptism)
- "உறுதிப்பூசுதல்" / "அபிஷேகம்" -> Confirmation (tabConfirmation)
- "திருமணம்" / "விவாகம்" / "கல்யாணம்" -> Marriage / Holy Matrimony (tabMarriage)
- "நோயில் பூசுதல்" / "கடைசிப் பூசுதல்" / "தைலம்" -> Anointing of the Sick (tabAnointing Of Sick)
- "அடக்கம்" / "மரணப் பதிவு" / "மரித்தவர்கள்" -> Christian Burial / Death (tabDeath)
- "நபர்கள்" / "பங்கினர்" / "விசுவாசிகள்" / "உறுப்பினர்கள்" -> Members / Parishioners (tabMember)
- "குடும்பங்கள்" / "குடும்பம்" -> Families (tabFamily)
- "அன்பியம்" / "அன்பியங்கள்" -> BCC / Basic Christian Communities (tabFamily)
- "பங்கு" / "பங்குகள்" -> Parish / Parishes (tabParish)
- "மறைமாவட்டம்" -> Diocese (tabDiocese)
- "மறைவட்டம்" -> Vicariate (tabVicariate)

Examples:
- "இந்த வருடம் எத்தனை நபர்கள் புது நன்மை எடுத்துள்ளனர்?" -> "How many members received First Holy Communion this year?"
- "போன வருடம் நடந்த திருமணங்களில் Clinton-ன் பேரில் யாருக்கும் திருமணம் நடந்ததா?" -> "Find marriage records for Clinton in marriage register"
- "Clinton திருமணம் நடந்ததா?" -> "Find marriage records for Clinton in marriage register"
- "கடந்த வருடம் மொத்தம் எத்தனை பேர் புதுப்பணி எடுத்தார்கள் அவர்களின் list மற்றும் family code-ஐ இரண்டையும் குறிப்பிடவும்" -> "List members who received First Holy Communion last year with their names and family card number (family_card_no)"
- "கடந்த வருடம் புது நன்மை எடுத்தவர்கள் பட்டியல் மற்றும் குடும்ப அட்டை எண்" -> "List members who received First Holy Communion last year with their names and family card number (family_card_no)"
- "இந்த ஆண்டு மொத்தம் எத்தனை நபர்கள் இறந்தார்கள் மற்றும் அவர்களின் பரிஷ் பெயரை குறிப்பிடவும்" -> "List members who died this year with their parish name from death register"
- "புது நன்மை பெற்றவர்கள் பட்டியல்" -> "List of members who received First Holy Communion"
- "2024-ல் ஞானஸ்நானம் பெற்ற குழந்தைகள்" -> "List of children baptized in 2024"
- "உறுதிப்பூசுதல் பெற்றவர்கள் எத்தனை பேர்" -> "Count of members who received Confirmation"
- "shwo all merriage recrods" -> "Show all marriage records"
- "list membes who completed babtizum in 2024" -> "List members who completed baptism in 2024"
- "who is the famly hed in st joshep parsh" -> "Who is the family head in St. Joseph Parish"
- "how many familys in lourdu matha bcc" -> "How many families in Lourdu Matha BCC"

CRITICAL RULES:
1. Return ONLY the translated, corrected English question string.
2. Do NOT add quotes, markdown, explanations, or any extra text.
3. Preserve all specific numbers, years, proper names, and parish names."""),
    ("human", "{question}"),
])

def clean_church_query_text(text: str) -> str:
    if not text:
        return text
    # Specialized phonetic & speech-to-text cleaner for Tamil/English Catholic Church queries
    fixes = [
        (r'\bபுதுப்?\s*பணி\b', 'First Holy Communion (புது நன்மை)'),
        (r'\bபுதுப்பணி\b', 'First Holy Communion (புது நன்மை)'),
        (r'\bபுதுபணி\b', 'First Holy Communion (புது நன்மை)'),
        (r'\bpudupani\b', 'First Holy Communion'),
        (r'\bpudu\s*pani\b', 'First Holy Communion'),
        (r'\bபுது\s*நன்மை\b', 'First Holy Communion (புது நன்மை)'),
        (r'\bபுதுநன்மை\b', 'First Holy Communion (புது நன்மை)'),
        (r'\bமுதல்\s*நற்கருணை\b', 'First Holy Communion (முதல் நற்கருணை)'),
        (r'\bநற்கருணை\b', 'First Holy Communion (நற்கருணை)'),
        (r'\bkalyanam\b', 'Marriage'),
        (r'\bகல்யாண[ம்ா]?\b', 'Marriage (திருமணம்)'),
        (r'\bதிருமணம்\b', 'Marriage (திருமணம்)'),
        (r'\bவிவாகம்\b', 'Marriage (விவாகம்)'),
        (r'\bஞானஸ்தானம்\b', 'Baptism (ஞானஸ்நானம்)'),
        (r'\bஞான\s*ஸ்தானம்\b', 'Baptism (ஞானஸ்நானம்)'),
        (r'\bஞானஸ்நானம்\b', 'Baptism (ஞானஸ்நானம்)'),
        (r'\bஞானஸ்நான\b', 'Baptism (ஞானஸ்நான)'),
        (r'\bதிருமுழுக்கு\b', 'Baptism (திருமுழுக்கு)'),
        (r'\bமாமோதீசா\b', 'Baptism (மாமோதீசா)'),
        (r'\bஉறுதிப்?\s*பூசுதல்\b', 'Confirmation (உறுதிப்பூசுதல்)'),
        (r'\bநோயில்\s*பூசுதல்\b', 'Anointing of the Sick (நோயில் பூசுதல்)'),
        (r'\bகடைசிப்\s*பூசுதல்\b', 'Anointing of the Sick (நோயில் பூசுதல்)'),
        (r'\bஅடக்கம்\b', 'Christian Burial Death (அடக்கம்)'),
        (r'\bமரணப்\s*பதிவு\b', 'Death Register (மரணப் பதிவு)'),
        (r'\bமரித்தவர்கள்\b', 'Death Register (மரித்தவர்கள்)'),
        (r'\bcarrots?\b', 'vicars'),
        (r'\bkarots?\b', 'vicars'),
        (r'\bparis-?கள்\b', 'parishes'),
        (r'\bparis\b', 'parish'),
        (r'\bpariss\b', 'parish'),
        (r'\bpaaris\b', 'parish'),
        (r'\bபரிஷ்\b', 'parish'),
        (r'\bபாரிஸ்\b', 'parish'),
        (r'\bdiocess\b', 'diocese'),
        (r'\bdie access\b', 'diocese'),
        (r'\bbabtizum\b', 'baptism'),
        (r'\bbapthism\b', 'baptism'),
        (r'\bbapthisam\b', 'baptism'),
        (r'\bunion\b', 'communion'),
        (r'\bcnf\b', 'confirmation'),
        (r'\bmrg\b', 'marriage'),
        (r'\banbiyam\b', 'BCC'),
        (r'\banbiyangal\b', 'BCCs'),
        (r'\bfamily\s*code\b', 'family card number (family_card_no)'),
        (r'\bகுடும்ப\s*கோடு\b', 'family card number (family_card_no)'),
        (r'\bகுடும்ப\s*அட்டை\b', 'family card number (family_card_no)'),
        (r'\bகடந்த\s*(?:வருடம்|ஆண்டு)\b', 'last year'),
        (r'\bபோன\s*வருடம்\b', 'last year'),
    ]
    cleaned = text
    for pat, rep in fixes:
        cleaned = re.sub(pat, rep, cleaned, flags=re.IGNORECASE)
    return cleaned

def enhance_query_node(state: GraphState) -> GraphState:
    question = clean_church_query_text(state["question"].strip())
    history = state.get("history", [])
    reference_text = (state.get("reference_text") or "").strip()
    
    reference_keywords = ["them", "they", "those", "these", "their", "him", "her", "it", "list them", "show them", "the same", "above", "this", "that", "next", "more", "remaining", "page", "next records", "next 50", "next page"]
    q_lower = question.lower()
    has_reference_keyword = any(re.search(r'\b' + re.escape(kw) + r'\b', q_lower) for kw in reference_keywords)
    
    # 1. If the user explicitly referenced a message/quote OR the query has reference pronouns with history:
    if reference_text or (history and has_reference_keyword):
        print(f"[enhance_query] Extending query with reference & spelling correction: question='{question}', reference='{reference_text}'")
        
        history_lines = []
        if reference_text:
            history_lines.append(f"Referenced Context / Quote: {reference_text}")
        for msg in history[-3:]:
            role = "User" if msg.get("role") == "user" else "Assistant"
            history_lines.append(f"{role}: {msg.get('content', '')[:500]}")
        history_context = "\n".join(history_lines)

        try:
            response = invoke_llm_with_rotation(ENHANCE_QUERY_PROMPT.format_messages(
                reference_context=history_context,
                question=question
            ))
            enhanced = response.content.strip().strip('"').strip("'")
            print(f"[enhance_query] Extended & Corrected Question: '{enhanced}'")
        except Exception as e:
            print(f"[enhance_query] Warning in reference enhancement: {e}")
            enhanced = question

        embedding = embed_text(enhanced)
        return {**state, "enhanced_query": enhanced, "query_embedding": embedding}

    # 2. Standalone question: Automatic Background Spelling & Terminology Correction
    print(f"[enhance_query] Automatic background spelling & grammar enhancement for prompt: '{question}'")
    
    # Fast church keyword dictionary corrections
    corrections = {
        "babtism": "Baptism", "babtized": "Baptized", "baptizm": "Baptism", "parsh": "Parish",
        "marige": "Marriage", "marrige": "Marriage", "mariage": "Marriage", "famly": "Family",
        "famlies": "Families", "comunion": "Holy Communion", "dioce": "Diocese", "diocis": "Diocese",
        "membr": "Member", "membrs": "Members", "st josef": "St. Joseph's"
    }
    
    try:
        response = invoke_llm_with_rotation(STANDALONE_ENHANCE_PROMPT.format_messages(question=question))
        enhanced = response.content.strip().strip('"').strip("'")
        print(f"[enhance_query] Automatically Enhanced Question: '{enhanced}'")
    except Exception as e:
        print(f"[enhance_query] Fallback dictionary correction: {e}")
        words = question.split()
        fallback_words = [corrections.get(w.lower(), w) for w in words]
        enhanced = " ".join(fallback_words)
        
    embedding = embed_text(enhanced)
    return {**state, "enhanced_query": enhanced, "query_embedding": embedding}

def retrieve_context_node(state: GraphState) -> GraphState:
    print("[retrieve_context] Retrieving schema context and few-shots...")
    relevant_tables = fetch_relevant_schemas(state["question"], state["enhanced_query"], state["query_embedding"])
    combined_query = f"{state['question']} {state['enhanced_query']}"
    relevant_fields = fetch_relevant_fields(state["query_embedding"], combined_query)
    few_shots = fetch_few_shot_examples(state["query_embedding"])
    return {**state, "relevant_tables": relevant_tables, "relevant_fields": relevant_fields, "few_shot_examples": few_shots}

SQL_GEN_PROMPT = ChatPromptTemplate.from_messages([
    ("system", r"""You are an expert MariaDB SQL query writer for the KOINONIA Parish Assistant app.

## Database Tables and Relationships
You are querying a MariaDB database with the following custom tables:
{relevant_tables}

## Relevant Fields (Semantically Matched Columns)
Use these exact column names when matching user concepts:
{relevant_fields}

{few_shot_examples}

---
## USER JURISDICTION & ROLE-BASED ACCESS CONTROL RULES:
User Role: {user_role}
Assigned Diocese: {user_diocese}
Assigned Parish: {user_parish}
Assigned Vicariate: {user_vicariate}

### A. Global Administrator & System Manager Queries (Unrestricted Across All Dioceses):
1. If User Role is "Administrator" or "System Manager":
   - Full global access across all 5 dioceses (Trichy, Salem, Chennai, Vellore, Coimbatore) and all 20 parishes.
   - Do NOT inject any diocese or parish filter unless the user explicitly names one in their question.
   - "Total members" / "Total members across all dioceses" → `SELECT COUNT(*) AS total_members FROM tabMember`
   - "List all parishes" → `SELECT name AS parish_name, diocese_id, patron_saint, parish_priest, city FROM tabParish`
   - "Count members in each diocese" → `SELECT diocese_id, COUNT(*) AS total_members FROM tabMember GROUP BY diocese_id ORDER BY total_members DESC`
   - "Total families" / "Show families" → `SELECT parish_id AS parish_name, COUNT(*) AS total_families FROM tabFamily GROUP BY parish_id ORDER BY total_families DESC`
   - "Show total counts of all sacraments" → `SELECT 'Baptism' AS sacrament_name, COUNT(*) AS total_count FROM tabBaptism UNION ALL SELECT 'First Holy Communion' AS sacrament_name, COUNT(*) AS total_count FROM tabCommunion UNION ALL SELECT 'Confirmation' AS sacrament_name, COUNT(*) AS total_count FROM tabConfirmation UNION ALL SELECT 'Marriage' AS sacrament_name, COUNT(*) AS total_count FROM tabMarriage UNION ALL SELECT 'Death' AS sacrament_name, COUNT(*) AS total_count FROM tabDeath UNION ALL SELECT 'Anointing Of Sick' AS sacrament_name, COUNT(*) AS total_count FROM \`tabAnointing Of Sick\``

### B. Diocesan & Parish Queries (Permitted for ALL Roles in their Diocese):
1. Questions about `tabParish`, `tabDiocese`, `tabVicariate` (such as parish directory, church history, patron saint, feast days, parish priest, assistant priest, bishop name):
   - Scope to `{user_diocese}`:
     - "How many parishes in my diocese?" → `SELECT COUNT(*) FROM tabParish WHERE diocese_id = '{user_diocese}'`
     - "List parishes in my diocese" → `SELECT name AS parish_name, patron_saint, feast_day, parish_priest, city FROM tabParish WHERE diocese_id = '{user_diocese}'`
     - "How many vicar generals in my diocese?" / "How many vicariates?" → `SELECT COUNT(DISTINCT vicariate_id) AS total_vicariates FROM tabParish WHERE diocese_id = '{user_diocese}' AND vicariate_id IS NOT NULL`
     - "List vicar generals / vicariates in my diocese" → `SELECT DISTINCT vicariate_id AS vicariate_name, diocese_id FROM tabParish WHERE diocese_id = '{user_diocese}' AND vicariate_id IS NOT NULL`
     - "Tell me about my parish" / "History of my parish" → `SELECT name AS parish_name, patron_saint, feast_day, established_date, parish_priest, assistant_priest, city, note FROM tabParish WHERE name = '{user_parish}'`
     - "Tell me about [Parish Name]" → `SELECT name AS parish_name, patron_saint, feast_day, established_date, parish_priest, assistant_priest, city, note FROM tabParish WHERE name = '[Parish Name]' AND diocese_id = '{user_diocese}'`
     - "Tell me about my diocese" → `SELECT diocese_name, bishop_name, established_date, city, phone, email, note FROM tabDiocese WHERE name = '{user_diocese}'`

### B. Personal Parishioner & Sacrament Data (Strictly Role-Restricted):
2. If User Role is "Bishop", "Curia", "Vicar General", "Chancellor", "Administrator":
   - Full access strictly to records within their own assigned diocese (`{user_diocese}`).
   - If user asks for counts, gender breakdown, living status, sacraments, or general members (even if phrased "in my parish" or "in my diocese"):
     -> Scope with `WHERE diocese_id = '{user_diocese}'`.
     -> If grouping by gender: `SELECT gender, COUNT(*) AS total_members FROM tabMember WHERE diocese_id = '{user_diocese}' GROUP BY gender ORDER BY total_members DESC`.
     -> If grouping by living status: `SELECT living_status, COUNT(*) AS total_members FROM tabMember WHERE diocese_id = '{user_diocese}' GROUP BY living_status ORDER BY total_members DESC`.
     -> NEVER leave `parish_id = ''` or `parish_id = '{user_diocese}'` because `{user_diocese}` is a Diocese, not a Parish!
   - If user asks "in my parish" / "in my diocese" / "how many families" / "show families" without naming a single specific parish:
     -> Return parish-wise breakdown: `SELECT parish_id AS parish_name, COUNT(*) AS total_families FROM tabFamily WHERE diocese_id = '{user_diocese}' GROUP BY parish_id ORDER BY total_families DESC`.
   - If user names a specific parish within their diocese (e.g. "families in Christ the King Parish"):
     -> Filter `WHERE parish_id = 'Christ the King Parish' AND diocese_id = '{user_diocese}'`.
   - If user explicitly requests data or counts for ANOTHER diocese (e.g. asking for "Salem diocese", "Chennai diocese", "Vellore diocese", "Coimbatore diocese", etc.) that is NOT `{user_diocese}`:
     -> Return raw string: `UNAUTHORIZED_DIOCESE`.
3. If User Role is "Vicar Forane":
   - Restrict member and sacrament queries to their vicariate: `WHERE vicariate_id = '{user_vicariate}'`.
   - If user asks for member records across the entire diocese or other vicariates -> Return raw string: `UNAUTHORIZED_DIOCESE`.
4. If User Role is "Parish Priest":
   - If user asks for member/sacrament records across "ALL PARISHES", "ENTIRE DIOCESE", or "OTHER PARISHES" -> Return raw string: `UNAUTHORIZED_DIOCESE`.
   - Otherwise, ALWAYS filter personal tables strictly by their assigned parish (`{user_parish}`):
     - `bapt_parish_id = '{user_parish}'` (for tabBaptism)
     - `mrg_parish_id = '{user_parish}'` (for tabMarriage)
     - `cnf_parish_id = '{user_parish}'` (for tabConfirmation)
     - `fhc_parish_id = '{user_parish}'` (for tabCommunion)
     - `death_parish_id = '{user_parish}'` (for tabDeath)
     - `anointing_parish_id = '{user_parish}'` (for tabAnointing Of Sick)
     - `parish_id = '{user_parish}'` (for tabFamily / tabMember)
5. If User Role is "Parishioner":
   - Restrict personal tables strictly to their assigned parish (`parish_id = '{user_parish}'`).
   - If asking for other parishes -> Return raw string: `UNAUTHORIZED_DIOCESE`.

---
## TABLE SELECTION RULES (pick the right table for the question):
- MULTI-SACRAMENT / SACRAMENT COUNT / SUMMARY queries ("sacraments", "how many sacraments", "received sacraments", "sacrament count", "screments"):
  - For family sacrament queries: `SELECT family_card_no, bapt_parish_id AS parish_name, COUNT(*) AS total_sacraments FROM tabBaptism WHERE diocese_id = '{user_diocese}' AND family_card_no IS NOT NULL AND family_card_no != '' GROUP BY family_card_no, bapt_parish_id HAVING COUNT(*) <= 3 ORDER BY total_sacraments DESC LIMIT 50`
- BAPTISM queries ("baptized", "christened", "bapt date", "godfather", "godmother", "who baptized") → `tabBaptism`
- COMMUNION queries ("first communion", "FHC", "holy communion", "fhc date", "fhc minister", "புது நன்மை", "புதுநன்மை", "நற்கருணை", "முதல் நற்கருணை") → `tabCommunion` (ALWAYS query tabCommunion, NEVER tabMember)
- CONFIRMATION queries ("confirmed", "confirmation", "CNF", "cnf date", "sponsor", "cnf minister") → `tabConfirmation`
- MARRIAGE queries ("married", "wedding", "bride", "bridegroom", "groom", "solemnized", "mrg date", "திருமணம்", "கல்யாணம்"):
  - When searching for a person's marriage by name (e.g. "Clinton", "Thomas", "Maria"): ALWAYS search bridegroom and bride columns:
    `WHERE (bridegroom_name LIKE '%Clinton%' OR bridegroom_last_name LIKE '%Clinton%' OR bride_name LIKE '%Clinton%' OR bride_last_name LIKE '%Clinton%')`
  - Select: `SELECT bridegroom_name, bridegroom_middle_name, bridegroom_last_name, bride_name, bride_middle_name, bride_last_name, mrg_date, mrg_parish_id AS parish_name FROM tabMarriage`
  - Example: "Find marriage records for Clinton" -> `SELECT bridegroom_name, bridegroom_last_name, bride_name, bride_last_name, mrg_date, mrg_parish_id AS parish_name FROM tabMarriage WHERE diocese_id = '{user_diocese}' AND (bridegroom_name LIKE '%Clinton%' OR bridegroom_last_name LIKE '%Clinton%' OR bride_name LIKE '%Clinton%' OR bride_last_name LIKE '%Clinton%')`
- DEATH/BURIAL queries ("died", "death", "passed away", "buried", "burial", "deceased", "funeral", "cemetery", "last rites", "இறந்தார்கள்", "இறப்பு") → `tabDeath` (select first_name, middle_name, last_name, death_date, parish_id AS parish_name)
- ANOINTING queries ("anointing", "anointed", "sick anointing", "extreme unction") → `tabAnointing Of Sick` (always backtick-quote: \`tabAnointing Of Sick\`)
- MEMBER queries ("member", "parishioner", "person details", "blood group", "occupation", "education", "marital status", "living status", "who is [name]") → `tabMember`
- FAMILY queries ("family", "household", "family card", "BCC", "zone", "economic status", "income", "house type", "family register") → `tabFamily`
- DIOCESE queries ("diocese", "bishop", "ordinary", "diocesan", "established diocese") → `tabDiocese`
- VICARIATE queries ("vicariate", "deanery", "vicar forane", "dean", "forane") → `tabVicariate`
- PARISH queries ("parish", "church", "patron saint", "feast day", "parish priest", "assistant priest") → `tabParish`

---
## STRICT RELATIONSHIP RULES:

1. `tabMember` links to `tabFamily` via `tabMember.family_id = tabFamily.name`.
2. To find members in a Zone → JOIN tabMember with tabFamily on `tabMember.family_id = tabFamily.name`, filter `tabFamily.zone_id = 'Zone X'`. NEVER use `tabMember.district_id` for zone.
3. To find families/members in a BCC → filter `tabFamily.parish_bcc_id = '[BCC Name]'`. NEVER use `place_of_birth`.
4. To list parishes in a vicariate → `FROM tabParish WHERE vicariate_id = '[vicariate name]'`.
5. To list vicariates/parishes in a diocese → filter `diocese_id = '[diocese name]'`.
6. **CRITICAL — NO JOINS ON SACRAMENT TABLES**: NEVER JOIN `tabMember` or `tabFamily` with sacrament tables (`tabBaptism`, `tabCommunion`, `tabConfirmation`, `tabMarriage`, `tabAnointing Of Sick`, `tabDeath`). ALWAYS query sacrament tables DIRECTLY. They already contain first_name, last_name, father_name, mother_name, and gender. If the user asks for a chart or count by male/female, simply use `SELECT gender, COUNT(*) FROM [table_name] GROUP BY gender`.
7. Primary key column in all Frappe tables is `name` (NOT `id`).
8. NEVER use `parish_priest` to filter by Parish name. `parish_priest` stores the PRIEST'S NAME. Use `bapt_parish_id`, `mrg_parish_id`, `cnf_parish_id`, `fhc_parish_id`, `death_parish_id`, or `parish_id` to filter by parish name.

---
## DATE / YEAR RULES:

9. For a specific year ("in 2023", "during 2020", "2024 baptisms") → `WHERE YEAR([date_col]) = 2023`. **CRITICAL: NEVER replace a specific 4-digit year like 2024 with YEAR(CURDATE()), because the system clock might be in a different year (e.g. 2026). Always use the literal number.**
10. For "this year" / "current year" (without specifying the number) → `WHERE YEAR([date_col]) = YEAR(CURDATE())`.
11. For "this month" / "entered this month" / "added this month" → ALWAYS filter on the relevant sacrament/record date: `WHERE MONTH([date_col]) = MONTH(CURDATE()) AND YEAR([date_col]) = YEAR(CURDATE())` (e.g. `MONTH(bapt_date) = MONTH(CURDATE()) AND YEAR(bapt_date) = YEAR(CURDATE())` for tabBaptism).
12. For a specific month ("in January 2024", "March baptisms") → `WHERE MONTH([date_col]) = 1 AND YEAR([date_col]) = 2024`.
13. For date range ("between 2020 and 2023", "from 2018 to 2022") → `WHERE [date_col] BETWEEN '2020-01-01' AND '2023-12-31'`.
14. For recent records ("last 6 months", "recent", "past year") → `WHERE [date_col] >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)`.

---
## COUNT vs LIST RULES:

15. Count-only ("how many", "count", "total number of") → `SELECT COUNT(*) FROM ...` — no other columns unless GROUP BY is present. **SPECIAL FOR BISHOP**: When User Role is "Bishop" and the question asks "how many families/members in my diocese" or "how many families/members in my parish" (without specifying a single parish name), ALWAYS return the parish-wise breakdown table: `SELECT parish_id AS parish_name, COUNT(*) AS total_families FROM tabFamily WHERE diocese_id = '{user_diocese}' GROUP BY parish_id ORDER BY total_families DESC`.
16. List / Show Records queries ("show", "list", "display", "find", "give me", "who are", "show records", "list records", "show baptism records", "show marriage records", "details") → ALWAYS select human-readable row columns (e.g. for tabBaptism: `SELECT first_name, middle_name, last_name, bapt_date, father_name, mother_name FROM tabBaptism WHERE ... LIMIT 50`). **CRITICAL: NEVER use COUNT(*) when the user asks to "show records", "list records", or "get details" — you MUST return the actual list of rows/persons.**
17. Grouped count ("by parish", "per zone", "breakdown by BCC", "parish-wise count", "statistics by year") → `SELECT [group_col], COUNT(*) FROM ... GROUP BY [group_col] ORDER BY COUNT(*) DESC`. **CRITICAL FOR PARISH BREAKDOWNS:** When grouping by `parish_id` or `bapt_parish_id`, ALWAYS include `parish_id IS NOT NULL AND parish_id != ''` in the WHERE clause so unassigned/NULL parish records do not produce an empty '-' row in the parish list table.
18. "How many AND list them" → return just the list (individual columns, no COUNT(*)).
19. Chart/plot queries ("bar chart", "pie chart", "plot", "trend", "graph") → `SELECT [label_col], COUNT(*) AS count FROM ... GROUP BY [label_col] ORDER BY [label_col]`. **CRITICAL FOR CHARTS:** You MUST return exactly TWO columns: one label column and one numeric count column. NEVER return pivoted conditional counts (like `COUNT(CASE WHEN gender='Male')`). For gender charts, ALWAYS use `SELECT gender, COUNT(*) FROM tabBaptism GROUP BY gender`.
20. MULTI-METRIC / COMPOUND QUESTIONS ("how many parishes, how many members, and how many vicariates?", "total parishes + total members + total vicars"):
    - NEVER write multiple SELECT statements separated by semicolons (`;`), as MariaDB only executes a single statement.
    - ALWAYS combine multi-count questions into a SINGLE query using `UNION ALL` or scalar subqueries, for example:
      `SELECT 'Total Parishes' AS metric, COUNT(*) AS count FROM tabParish WHERE enabled = 1 UNION ALL SELECT 'Total Members' AS metric, COUNT(*) AS count FROM tabMember UNION ALL SELECT 'Total Vicariates' AS metric, COUNT(DISTINCT vicariate_id) AS count FROM tabParish WHERE vicariate_id IS NOT NULL AND vicariate_id != ''`
      OR
      `SELECT (SELECT COUNT(*) FROM tabParish WHERE enabled = 1) AS total_parishes, (SELECT COUNT(*) FROM tabMember) AS total_members, (SELECT COUNT(DISTINCT vicariate_id) FROM tabParish WHERE vicariate_id IS NOT NULL AND vicariate_id != '') AS total_vicariates`

---
## FILTERING RULES:

20. By minister/priest name ("baptisms by Fr. Thomas", "burial by [minister]") → `WHERE bapt_minister LIKE '%Thomas%'` (use LIKE for partial name matching).
21. By godfather/godmother/sponsor → `WHERE bapt_god_father LIKE '%[name]%'` (baptism), `cnf_god_father` (confirmation), `sponsor` (confirmation), `witness1_name` / `witness2_name` (marriage).
22. By gender ("female members", "boys baptized", "girls confirmed") → `WHERE gender = 'Female'` or `WHERE gender = 'Male'`.
23. By living status ("alive", "deceased members") → `WHERE living_status = 'Alive'` or `WHERE living_status = 'Deceased'` in tabMember.
24. By person's name ("details of Paul Amalraj S.", "find Paul Amalraj", "tell me about Thomas D'Souza", "Nirmala Fernando G.") → Note: first_name is given name (e.g. Paul), middle_name is family/father name (e.g. Amalraj), last_name is initial (e.g. S.). Search using exact full-name matching: `WHERE CONCAT_WS(' ', first_name, NULLIF(middle_name, ''), last_name) LIKE '%[first]%[middle/surname]%' OR (first_name = '[first]' AND middle_name = '[middle/surname]')`. Do NOT use loose `OR first_name LIKE '%[first]%'` without surname when a surname was given, to avoid returning unrelated people with the same first name. For single name search with only one word ("Celine"), use `WHERE (first_name = 'Celine' OR middle_name = 'Celine' OR last_name = 'Celine')`.
25. By family card number → `WHERE family_card_no = '[card_no]'` (exists in all sacrament tables) or `family_register_number` (tabFamily).
26. By Diocese/Vicariate scope ("families in Vellore diocese", "records in Chennai vicariate") → filter `diocese_id = '[diocese name]'` or `vicariate_id = '[vicariate name]'`. These columns exist in tabFamily, tabMember, tabBaptism, tabConfirmation, tabCommunion, tabMarriage, tabDeath.
27. By marital status ("single members", "widowed members") → `WHERE marital_status_id = 'Single'` in tabMember; `WHERE marital_status = 'Widowed'` in tabDeath.
28. By occupation ("teachers in parish", "farmers", "members who are doctors") → `WHERE occupation LIKE '%teacher%'` in tabMember.
29. By economic status ("poor families", "affluent households", "below poverty line") → `WHERE economic_status LIKE '%Poor%'` in tabFamily.
30. By cause of death ("died of cancer", "accidents", "old age") → `WHERE death_cause LIKE '%cancer%'` in tabDeath.
31. By cemetery ("buried in St. Joseph cemetery") → `WHERE cemetery_code LIKE '%St. Joseph%'` in tabDeath.
32. Register reference ("baptism register ref ABC-001", "marriage register no") → `WHERE bapt_register_ref = 'ABC-001'` (tabBaptism), `mrg_register_ref` (tabMarriage), `cnf_register_ref` (tabConfirmation), `fhc_register_ref` (tabCommunion), `death_register_ref` (tabDeath).
33. Patron saint queries ("parishes with patron saint Mary", "feast day in January") → `WHERE patron_saint LIKE '%Mary%'` or `WHERE MONTH(feast_day) = 1` in tabParish.
34. Active/inactive records ("active parishes", "inactive families") → `WHERE active = 1` (active) or `WHERE active = 0` (inactive).
35. Family head ("head of family", "who is the family head") → `WHERE is_family_head = 'Yes'` in tabMember.
36. Bride/groom religion ("inter-religion marriages", "non-Catholic groom") → `WHERE bridegroom_religion_id != 'Catholic'` or `bride_religion_id` in tabMarriage.
37. Members who completed multiple sacraments ("members who completed baptism and communion and confirmation", "fully initiated members", "married members with all sacraments") → Query `tabMember` directly using `WHERE bapt_date IS NOT NULL AND fhc_date IS NOT NULL AND cnf_date IS NOT NULL` (and add `AND marital_status_id = 'Married'` if marriage is mentioned). NEVER try to JOIN all 4 sacrament tables together.
38. Person / Member lookups ("tell me about [name]", "who is [name]", "find [name]", "search [name]", "telll me about [name]") → Check `tabMember` (e.g. `SELECT first_name, middle_name, last_name, dob, gender, living_status, parish_id, mobile FROM tabMember WHERE CONCAT_WS(' ', first_name, NULLIF(middle_name, ''), last_name) LIKE '%[first]%[last]%' OR (first_name = '[first]' AND middle_name = '[last]')`) or sacrament table if sacrament is mentioned.
39. Names with apostrophes (e.g. D'Souza, O'Connor, St. Mary's) → Always escape single quotes in SQL string literals: `middle_name = 'D\\\'Souza'` or `last_name = 'D\\\'Souza'` or `LIKE '%Souza%'`.
40. Family details of a person / family members:
    - To list all family members of a family ID → `SELECT m.first_name, m.middle_name, m.last_name, m.relationship_id, m.gender, m.age, m.living_status FROM tabMember m WHERE m.family_id = '[family_id]'`
    - To find family of a person → `SELECT m.first_name, m.middle_name, m.last_name, m.relationship_id, m.gender, m.age, m.living_status, f.parish_bcc_id, f.zone_id, f.family_register_number FROM tabMember m LEFT JOIN tabFamily f ON m.family_id = f.name WHERE m.family_id = (SELECT family_id FROM tabMember WHERE CONCAT_WS(' ', first_name, NULLIF(middle_name, ''), last_name) LIKE '%[first]%[middle/surname]%' OR (first_name = '[first]' AND middle_name = '[middle/surname]') LIMIT 1) OR (CONCAT_WS(' ', m.first_name, NULLIF(m.middle_name, ''), m.last_name) LIKE '%[first]%[middle/surname]%')`. NEVER join `tabBaptism` or other sacrament tables for family lookups!
41. Wildcards in SELECT: NEVER use `SELECT *`, `SELECT T1.*`, or `SELECT T2.*`. Always explicitly select up to 5 specific column names (e.g. `SELECT m.first_name, m.middle_name, m.last_name, f.parish_bcc_id, f.zone_id`).
42. Relationship between two persons ("how is [Name 1] related to [Name 2]?", "relationship between [Name 1] and [Name 2]", "is [Name 1] related to [Name 2]?", "which parish they belongs to?"):
    - Always query: `SELECT CONCAT_WS(' ', m1.first_name, NULLIF(m1.middle_name, ''), m1.last_name) AS person1_fullname, m1.relationship_id AS relationship1, m1.parish_id AS parish_name, CONCAT_WS(' ', m2.first_name, NULLIF(m2.middle_name, ''), m2.last_name) AS person2_fullname, m2.relationship_id AS relationship2, m1.family_id, m1.diocese_id FROM tabMember m1 JOIN tabMember m2 ON m1.family_id = m2.family_id WHERE (CONCAT_WS(' ', m1.first_name, NULLIF(m1.middle_name, ''), m1.last_name) LIKE '%[first1]%' OR (m1.first_name LIKE '%[first1]%' AND (m1.middle_name LIKE '%[last1]%' OR m1.last_name LIKE '%[last1]%'))) AND (CONCAT_WS(' ', m2.first_name, NULLIF(m2.middle_name, ''), m2.last_name) LIKE '%[first2]%' OR (m2.first_name LIKE '%[first2]%' AND (m2.middle_name LIKE '%[last2]%' OR m2.last_name LIKE '%[last2]%'))) LIMIT 1`.
43. Diocese Profile & History for a SINGLE diocese ("tell about [Diocese] diocese", "tell about Tiruchy diocese", "about Salem diocese", "diocese history", "who is the bishop of [Diocese]", "chancery details"):
    - Always query `tabDiocese`: `SELECT diocese_name, bishop_name, established_date, city, phone, email, website, note FROM tabDiocese WHERE (name LIKE '%[diocese]%' OR diocese_name LIKE '%[diocese]%' OR SOUNDEX(name) = SOUNDEX('[diocese]')) LIMIT 1`. Note: In tabDiocese, primary key name is 'Trichy', 'Salem', 'Chennai', 'Vellore', 'Coimbatore'.
48. Listing all Dioceses ("list all dioceses", "list them" when following a diocese query, "show all dioceses", "what are the dioceses", "names of all dioceses", "list dioceses"):
    - Always query `tabDiocese`: `SELECT diocese_name, bishop_name, established_date, city, phone, email FROM tabDiocese ORDER BY diocese_name ASC`. NEVER put `LIMIT 1` or single diocese filter when asked to list all dioceses!
44. Vicar General & Vicar Forane controlled parishes queries ("what are my controlled parishes", "list parishes in my vicariate", "parishes under my administration", "my vicariate parishes"):
    - Always query `tabParish`: `SELECT name AS parish_name, city, patron_saint, parish_priest, established_date FROM tabParish WHERE (vicariate_id = '{user_vicariate}' OR diocese_id = '{user_diocese}') LIMIT 50`.
47. Pagination & Next Records queries ("show next 50 records", "next records", "next page", "show remaining records", "page 2", "show next batch"):
    - Identify the base SELECT query from the enhanced context and append or update `LIMIT 50 OFFSET 50` (or `OFFSET 100` for page 3).
    - Example: `SELECT m.first_name, m.last_name, m.gender, m.age FROM tabMember WHERE diocese_id = '{user_diocese}' LIMIT 50 OFFSET 50`.
45. Multi-Sacrament Counts / Summary ("count of each sacrament", "sacrament summary", "sacrament statistics", "add the sacraments name", "breakdown by sacrament", "sacrament counts"):
    - Always use UNION ALL with explicit sacrament names:
      `SELECT 'Baptism' AS sacrament_name, COUNT(*) AS total_count FROM tabBaptism WHERE (bapt_parish_id = '{user_parish}' OR diocese_id = '{user_diocese}') UNION ALL SELECT 'First Holy Communion' AS sacrament_name, COUNT(*) AS total_count FROM tabCommunion WHERE (fhc_parish_id = '{user_parish}' OR diocese_id = '{user_diocese}') UNION ALL SELECT 'Confirmation' AS sacrament_name, COUNT(*) AS total_count FROM tabConfirmation WHERE (cnf_parish_id = '{user_parish}' OR diocese_id = '{user_diocese}') UNION ALL SELECT 'Marriage' AS sacrament_name, COUNT(*) AS total_count FROM tabMarriage WHERE (mrg_parish_id = '{user_parish}' OR diocese_id = '{user_diocese}') UNION ALL SELECT 'Death' AS sacrament_name, COUNT(*) AS total_count FROM tabDeath WHERE (death_parish_id = '{user_parish}' OR diocese_id = '{user_diocese}') UNION ALL SELECT 'Anointing Of Sick' AS sacrament_name, COUNT(*) AS total_count FROM `tabAnointing Of Sick` WHERE (anointing_parish_id = '{user_parish}' OR diocese_id = '{user_diocese}')`

---
## QUERY GENERATION RULES:
- ONLY write SELECT queries. NEVER write INSERT, UPDATE, DELETE, or ALTER queries.
- NEVER use `SELECT *` or unhelpful system columns (name, creation, modified, modified_by, owner, docstatus, idx, amended_from, _user_tags, _comments, _assign, _liked_by, custom).
- Select a MAXIMUM of 5-6 columns that directly answer the query.
- When querying sacrament or member registers (e.g. Baptism, Communion, Confirmation, Marriage, Death, Anointing, Member), ALWAYS include the candidate/person name (first_name, last_name, or bridegroom_name, bride_name) and the sacrament date (bapt_date, mrg_date, fhc_date, cnf_date, death_date) in the SELECT list, alongside requested fields (such as father_name, mother_name, minister).
- Return all matching records for the query.
- Do NOT guess or invent column names. Only use columns from the schemas above.
- Do NOT wrap SQL in markdown or code blocks. Return only the raw SQL string.
- If the question cannot be answered with these tables, return "UNSUPPORTED".
"""),
    ("human", "User question: {enhanced_query}"),
])

def generate_sql_node(state: GraphState) -> GraphState:
    print("[generate_sql] Generating SQL query...")
    
    q_raw = (state.get("question") or "").lower()
    q_enhanced = (state.get("enhanced_query") or "").lower()
    q_combined = f"{q_raw} {q_enhanced}"
    
    user_role = state.get("user_role") or "Parish Priest"
    
    is_count_query = any(k in q_combined for k in [
        "count", "how many", "total number", "total members", "total families", 
        "total baptisms", "total marriages", "statistics", "how much", "number of",
        "total count", "count of"
    ])
    
    # Pre-check for non-Bishop roles requesting diocese-wide / all-parishes data (only for detailed DATA queries, NOT counts)
    is_global = user_role in ["Bishop", "Curia", "Chancellor", "Administrator", "System Manager"]
    broad_diocese_keywords = [
        "all parishes", "entire diocese", "whole diocese", "across all parishes", 
        "every parish", "all the diocese", "all parishes in the diocese", "other parishes"
    ]
    
    if not is_global and not is_count_query and any(kw in q_combined for kw in broad_diocese_keywords):
        print(f"[generate_sql] Access Restricted: {user_role} requested broad diocese personal data: raw='{q_raw}', enhanced='{q_enhanced}'")
        return {**state, "generated_sql": "UNAUTHORIZED_DIOCESE"}

    # Check for unauthorized parish request if user is Vicar General / Vicar Forane / Parish Priest (only for detailed DATA queries, NOT counts)
    user_parishes = state.get("user_parishes") or []
    user_parish = (state.get("user_parish") or "").strip()
    
    if not is_count_query:
        if user_role in ["Vicar General", "Vicar Forane"] and user_parishes:
            import frappe
            all_parish_names = frappe.db.sql_list("SELECT name FROM tabParish") if frappe.db.table_exists("Parish") else []
            for p in all_parish_names:
                if p not in user_parishes:
                    short_p = p.replace("Parish", "").replace("Church", "").replace("Cathedral", "").strip()
                    if short_p and len(short_p) > 3 and re.search(r'\b' + re.escape(short_p.lower()) + r'\b', q_combined):
                        print(f"[generate_sql] Access Restricted: Vicar General requested unauthorized parish data '{p}'")
                        return {**state, "generated_sql": "UNAUTHORIZED_PARISH"}
                        
        elif user_role in ["Parish Priest", "Parishioner"] and user_parish:
            import frappe
            all_parish_names = frappe.db.sql_list("SELECT name FROM tabParish") if frappe.db.table_exists("Parish") else []
            for p in all_parish_names:
                if p.lower() != user_parish.lower():
                    short_p = p.replace("Parish", "").replace("Church", "").replace("Cathedral", "").strip()
                    if short_p and len(short_p) > 3 and re.search(r'\b' + re.escape(short_p.lower()) + r'\b', q_combined):
                        print(f"[generate_sql] Access Restricted: {user_role} of {user_parish} requested unauthorized parish data '{p}'")
                        return {**state, "generated_sql": "UNAUTHORIZED_PARISH"}

    # Pre-check for foreign diocese or foreign parish requests (e.g., Bishop of Salem asking for Christ the King Parish in Trichy)
    user_diocese = (state.get("user_diocese") or "Trichy").strip()
    
    import frappe
    if frappe.db.table_exists("Parish"):
        all_parishes = frappe.db.sql("SELECT name, diocese_id FROM tabParish", as_dict=True)
        for p in all_parishes:
            p_name = p.get("name") or ""
            p_dio = p.get("diocese_id") or ""
            short_p = p_name.replace("Parish", "").replace("Church", "").replace("Cathedral", "").replace("Shrine", "").strip()
            if short_p and len(short_p) > 3 and re.search(r'\b' + re.escape(short_p.lower()) + r'\b', q_combined):
                if user_diocese and p_dio and p_dio.lower() != user_diocese.lower():
                    print(f"[generate_sql] Access Restricted: User {user_role} of {user_diocese} requested parish '{p_name}' in foreign diocese '{p_dio}'")
                    return {
                        **state, 
                        "generated_sql": "UNAUTHORIZED_DIOCESE", 
                        "requested_foreign_parish": p_name, 
                        "requested_foreign_diocese": p_dio
                    }

    known_dioceses = [
        "trichy", "chennai", "vellore", "salem", "coimbatore", "madurai", 
        "tuticorin", "thanjavur", "kottar", "palayamkottai", "ooty", 
        "dharmapuri", "kumbakonam", "tirunelveli", "kuzhithurai", "sivagangai", "dindigul"
    ]
    for d in known_dioceses:
        if user_diocese and d != user_diocese.lower():
            # Match diocese name with word boundary (including Tamil suffixes like "salem diocese-ல", "salem-la", "salem")
            if re.search(r'\b' + re.escape(d) + r'(\b|[-_])', q_combined, re.IGNORECASE):
                print(f"[generate_sql] Access Restricted: User {user_role} of {user_diocese} requested unauthorized diocese '{d}': raw='{q_raw}'")
                return {**state, "generated_sql": "UNAUTHORIZED_DIOCESE", "requested_foreign_diocese": d.title()}

    parish_context = state.get("user_parish") or ""
    if user_role in ["Vicar General", "Vicar Forane"] and user_parishes:
        parish_context = "IN (" + ", ".join([f"'{p}'" for p in user_parishes]) + ")"

    prompt_msgs = SQL_GEN_PROMPT.format_messages(
        relevant_tables="\n\n".join(state["relevant_tables"]),
        relevant_fields="\n".join(state["relevant_fields"]),
        few_shot_examples=state["few_shot_examples"],
        user_role=state.get("user_role") or "Parish Priest",
        user_diocese=state.get("user_diocese") or "Trichy",
        user_parish=parish_context,
        user_vicariate=state.get("user_vicariate") or "",
        user_member_id=state.get("user_member_id") or "",
        user_email=state.get("user_email") or "",
        enhanced_query=state["enhanced_query"]
    )
    
    response = invoke_llm_with_rotation(prompt_msgs)
    content = response.content.strip()
    if "```sql" in content:
        sql = content.split("```sql")[1].split("```")[0].strip()
    elif "```" in content:
        sql = content.split("```")[1].strip()
    else:
        sql = content.strip()
        
    print(f"[generate_sql] SQL Generated:\n  {sql}")
    return {**state, "generated_sql": sql}

def sanitize_select_clause(sql: str, question: str = "") -> str:
    sql_upper = sql.upper().strip()
    if not sql_upper.startswith("SELECT") or "COUNT(" in sql_upper or "UNION" in sql_upper or "GROUP BY" in sql_upper:
        return sql
        
    table_match = re.search(r'FROM\s+`?(tab[A-Za-z0-9_ ]+)`?', sql, re.IGNORECASE)
    if not table_match:
        return sql
        
    table_name = table_match.group(1).strip().strip('`')
    
    preferred_cols = {
        "tabBaptism": ["first_name", "middle_name", "last_name", "bapt_date", "bapt_parish_id"],
        "tabCommunion": ["first_name", "middle_name", "last_name", "fhc_date", "fhc_parish_id"],
        "tabConfirmation": ["first_name", "middle_name", "last_name", "cnf_date", "cnf_parish_id"],
        "tabMarriage": ["bridegroom_name", "bridegroom_middle_name", "bridegroom_last_name", "bride_name", "mrg_date"],
        "tabAnointing Of Sick": ["first_name", "middle_name", "last_name", "anointing_date", "minister"],
        "tabDeath": ["first_name", "middle_name", "last_name", "death_date", "age"],
        "tabMember": ["first_name", "middle_name", "last_name", "relationship_id", "gender", "age", "family_id"],
        "tabFamily": ["family_register_number", "parish_bcc_id", "zone_id", "status", "parish_id"],
        "tabDiocese": ["diocese_name", "bishop_name", "established_date", "city", "phone", "email", "note"],
        "tabVicariate": ["vicariate_name", "diocese_id", "vicar_forane", "active"],
        "tabParish": ["parish_name", "patron_saint", "feast_day", "established_date", "parish_priest", "assistant_priest", "city", "note"]
    }
    
    # Check if wildcard is present anywhere in SELECT part
    select_part_raw = sql_upper.split("FROM")[0].replace("SELECT", "").strip()
    if "*" in select_part_raw:
        if "tabMember" in sql and "tabFamily" in sql:
            from_part_match = re.search(r'\bFROM\b.*', sql, re.IGNORECASE | re.DOTALL)
            if from_part_match:
                new_sql = f"SELECT m.first_name, m.middle_name, m.last_name, m.relationship_id, f.parish_bcc_id {from_part_match.group(0)}"
                if re.search(r'\btabMember\s+AS\s+T3\b|\btabMember\s+T3\b', sql, re.IGNORECASE):
                    new_sql = f"SELECT T3.first_name, T3.middle_name, T3.last_name, T3.relationship_id, T2.parish_bcc_id {from_part_match.group(0)}"
                print(f"[sanitize_select_clause] Converted JOIN wildcard to explicit columns: {new_sql}")
                return new_sql
        elif table_name in preferred_cols:
            cols_str = ", ".join(f"`{c}`" for c in preferred_cols[table_name])
            from_part_match = re.search(r'\bFROM\b.*', sql, re.IGNORECASE | re.DOTALL)
            if from_part_match:
                new_sql = f"SELECT {cols_str} {from_part_match.group(0)}"
                print(f"[sanitize_select_clause] Converted single-table wildcard to: {new_sql}")
                return new_sql

    if table_name in preferred_cols:
        select_part = sql_upper.split("FROM")[0].replace("SELECT", "").strip()
        selected_cols = [c.strip().strip('`') for c in select_part.split(",") if c.strip()]
        
        is_wildcard = "*" in select_part
        max_allowed = 8 if table_name in ["tabParish", "tabDiocese"] else 5
        has_too_many = len(selected_cols) > max_allowed
        
        core_fields = ["first_name", "bridegroom_name", "diocese_name", "vicariate_name", "parish_name", "family_name"]
        missing_core = not any(f.upper() in select_part for f in core_fields) and any(f in preferred_cols[table_name] for f in core_fields)
        
        if is_wildcard or has_too_many or missing_core:
            final_cols = list(preferred_cols[table_name])
            
            # Scan the original select_part for specific keywords requested (like mobile, email, phone, address, etc.)
            # and preserve them if they were selected in the original SQL
            special_keywords = ["mobile", "email", "phone", "address", "website", "established_date", "dob", "cemetery_code", "note", "assistant_priest"]
            for col in selected_cols:
                col_lower = col.lower()
                if any(kw in col_lower for kw in special_keywords):
                    # Extract the actual column name from any alias or prefix (e.g. t.mobile -> mobile)
                    base_col = col_lower.split(".")[-1].strip().strip('`')
                    if base_col not in final_cols:
                        final_cols.append(base_col)
            
            # Enforce column limit
            if len(final_cols) > max_allowed:
                final_cols = final_cols[:max_allowed]
                
            cols_str = ", ".join(f"`{c}`" for c in final_cols)
            from_part_match = re.search(r'\bFROM\b.*', sql, re.IGNORECASE | re.DOTALL)
            if from_part_match:
                from_part = from_part_match.group(0)
                new_sql = f"SELECT {cols_str} {from_part}"
                print(f"[sanitize_select_clause] Automatically polished SELECT clause from {len(selected_cols)} cols to: {new_sql}")
                return new_sql
                
    return sql

def sql_escape_str(val: str) -> str:
    if val is None:
        return ""
    return str(val).replace("'", "''")

def sql_quote_str(val: str) -> str:
    if val is None:
        return "''"
    return "'" + str(val).replace("'", "''") + "'"

def enforce_jurisdiction_sql_single(sql: str, state: GraphState) -> str:
    user_role = state.get("user_role") or "Parish Priest"
    user_diocese = state.get("user_diocese") or "Trichy"
    user_vicariate = state.get("user_vicariate") or ""
    user_parish = state.get("user_parish") or "Christ the King Parish"
    user_parishes = state.get("user_parishes") or []
    
    if user_role in ["Administrator", "System Manager"] or user_diocese in ["All Dioceses", "All"]:
        return sql
        
    sql_upper = sql.upper()
    if not sql_upper.startswith("SELECT") or sql in ["UNSUPPORTED", "UNAUTHORIZED_DIOCESE", "UNAUTHORIZED_PARISH"]:
        return sql
        
    alias_match = re.search(r'FROM\s+`?(tab[A-Za-z0-9_]+(?:\s+Of\s+Sick)?)`?(?:\s+(?:AS\s+)?([a-zA-Z0-9_]+))?', sql, re.IGNORECASE)
    if not alias_match:
        return sql
    table_name = alias_match.group(1).strip().strip('`')
    
    # Define column mappings for personal member & sacrament tables
    parish_col_map = {
        "tabBaptism": "bapt_parish_id",
        "tabMarriage": "mrg_parish_id",
        "tabConfirmation": "cnf_parish_id",
        "tabCommunion": "fhc_parish_id",
        "tabDeath": "death_parish_id",
        "tabAnointing Of Sick": "anointing_parish_id",
        "tabMember": "parish_id",
        "tabFamily": "parish_id"
    }
    
    conditions = []
    
    table_prefix = ""
    if alias_match.group(2) and alias_match.group(2).upper() not in ["WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "ON", "GROUP", "ORDER", "LIMIT", "SET", "VALUES"]:
        table_prefix = f"`{alias_match.group(2)}`."
    elif "JOIN" in sql_upper:
        table_prefix = f"`{table_name}`."

    user_diocese_esc = sql_escape_str(user_diocese)
    user_parish_esc = sql_escape_str(user_parish)
    user_vicariate_esc = sql_escape_str(user_vicariate)

    # 1. Diocese ID constraint (applies to ALL roles for any table with diocese_id)
    if user_diocese and "DIOCESE_ID" not in sql_upper and table_name in ["tabFamily", "tabMember", "tabBaptism", "tabMarriage", "tabConfirmation", "tabCommunion", "tabDeath", "tabAnointing Of Sick", "tabParish", "tabVicariate"]:
        conditions.append(f"{table_prefix}`diocese_id` = {sql_quote_str(user_diocese)}")
        
    is_pure_count = "COUNT(" in sql_upper and "FIRST_NAME" not in sql_upper and "LAST_NAME" not in sql_upper and "DOB" not in sql_upper and "MOBILE" not in sql_upper
    
    # 2. Vicariate / Controlled Parishes constraints for Vicar General & Vicar Forane (applied strictly to DATA queries)
    if not is_pure_count:
        if user_role in ["Vicar General", "Vicar Forane"]:
            if user_parishes and table_name in parish_col_map:
                parish_col = parish_col_map[table_name]
                parish_list_str = ", ".join([sql_quote_str(p) for p in user_parishes])
                # If the SQL used '=' with multiple parishes or used a comma in the string
                sql = re.sub(r"\b" + parish_col + r"\s*=\s*['\"][^'\"]*,[^'\"]*['\"]", f"{parish_col} IN ({parish_list_str})", sql, flags=re.IGNORECASE)
                sql = re.sub(r"\bparish_id\s*=\s*['\"][^'\"]*,[^'\"]*['\"]", f"parish_id IN ({parish_list_str})", sql, flags=re.IGNORECASE)
                sql_upper = sql.upper()
                
                # Check if any single controlled parish is explicitly matched
                has_valid_single_parish = any(sql_quote_str(p).upper() in sql_upper or f"'{p.upper()}'" in sql_upper or f'"{p.upper()}"' in sql_upper for p in user_parishes)
                if not has_valid_single_parish:
                    if f"{parish_col.upper()} IN" not in sql_upper and "PARISH_ID IN" not in sql_upper:
                        conditions.append(f"{table_prefix}`{parish_col}` IN ({parish_list_str})")
            elif user_parishes and table_name == "tabParish":
                parish_list_str = ", ".join([sql_quote_str(p) for p in user_parishes])
                if "NAME" not in sql_upper and "VICARIATE_ID" not in sql_upper:
                    conditions.append(f"{table_prefix}`name` IN ({parish_list_str})")
            
        # 3. Parish ID constraint for Parish Priest / Parishioner (for personal tables only)
        elif user_role in ["Parish Priest", "Parishioner"] and user_parish and table_name in parish_col_map:
            parish_col = parish_col_map[table_name]
            has_assigned_parish = (
                user_parish.upper() in sql_upper or 
                user_parish_esc.upper() in sql_upper or 
                sql_quote_str(user_parish).upper() in sql_upper or
                user_parish.replace("'", r"\'").upper() in sql_upper
            )
            # Replace any foreign parish filter that was generated with the user's assigned parish
            if parish_col.upper() in sql_upper or "PARISH_ID" in sql_upper:
                if not has_assigned_parish:
                    sql = re.sub(r"\b" + parish_col + r"\s*=\s*(?:'[^']*'|\"[^\"]*\")", f"{parish_col} = {sql_quote_str(user_parish)}", sql, flags=re.IGNORECASE)
                    sql = re.sub(r"\bparish_id\s*=\s*(?:'[^']*'|\"[^\"]*\")", f"parish_id = {sql_quote_str(user_parish)}", sql, flags=re.IGNORECASE)
                    sql_upper = sql.upper()
            else:
                conditions.append(f"{table_prefix}`{parish_col}` = {sql_quote_str(user_parish)}")
            
    if user_role in ["Bishop", "Curia", "Chancellor", "Administrator"]:
        # Strip accidental empty parish_id = '' or parish_id = '{user_diocese}'
        clean_sql_tmp = re.sub(r"\b(parish_id|bapt_parish_id|mrg_parish_id|cnf_parish_id|fhc_parish_id|death_parish_id)\s*=\s*['\"](?:|None|" + re.escape(user_diocese) + r"|" + re.escape(user_diocese_esc) + r")['\"]\s*(AND|OR)?\s*", "", sql, flags=re.IGNORECASE)
        clean_sql_tmp = re.sub(r"\s*(AND|OR)\s*(parish_id|bapt_parish_id|mrg_parish_id|cnf_parish_id|fhc_parish_id|death_parish_id)\s*=\s*['\"](?:|None|" + re.escape(user_diocese) + r"|" + re.escape(user_diocese_esc) + r")['\"]", "", clean_sql_tmp, flags=re.IGNORECASE)
        clean_sql_tmp = re.sub(r"\bWHERE\s+(GROUP\s+BY|ORDER\s+BY|LIMIT|\Z)", r" \1", clean_sql_tmp, flags=re.IGNORECASE)
        clean_sql_tmp = re.sub(r"\bWHERE\s*;\s*$", "", clean_sql_tmp, flags=re.IGNORECASE)
        clean_sql_tmp = re.sub(r"\bWHERE\s*$", "", clean_sql_tmp, flags=re.IGNORECASE)
        clean_sql_tmp = re.sub(r"\bWHERE\s+(AND|OR)\b", "WHERE", clean_sql_tmp, flags=re.IGNORECASE)
        sql = clean_sql_tmp.strip()
        sql_upper = sql.upper()

    if not conditions:
        return sql
        
    where_to_add = " AND ".join(conditions)
    
    # Strip any trailing semicolons or whitespace
    clean_sql = sql.strip().rstrip(';')
    
    # Identify positions of trailing clauses (GROUP BY, ORDER BY, LIMIT) using regex
    trailing_match = re.search(r'\b(GROUP\s+BY|ORDER\s+BY|LIMIT)\b', clean_sql, re.IGNORECASE)
    if trailing_match:
        trailing_pos = trailing_match.start()
    else:
        trailing_pos = len(clean_sql)
            
    head = clean_sql[:trailing_pos].strip()
    tail = clean_sql[trailing_pos:].strip()
    
    if re.search(r'\bWHERE\s*$', head, re.IGNORECASE):
        new_sql = f"{head} {where_to_add}"
    elif re.search(r'\bWHERE\b', head, re.IGNORECASE):
        new_sql = f"{head} AND {where_to_add}"
    else:
        new_sql = f"{head} WHERE {where_to_add}"
        
    if tail:
        new_sql = f"{new_sql} {tail}"
        
    print(f"[enforce_jurisdiction_sql] Injected scope filters: {new_sql}")
    return new_sql

def enforce_jurisdiction_sql(sql: str, state: GraphState) -> str:
    if not sql or sql in ["UNSUPPORTED", "UNAUTHORIZED_DIOCESE", "UNAUTHORIZED_PARISH"]:
        return sql
    sql_upper = sql.upper()
    if "UNION" in sql_upper:
        delimiter = "\nUNION ALL\n" if "UNION ALL" in sql_upper else "\nUNION\n"
        branches = re.split(r'\bUNION\s+(?:ALL\s+)?', sql, flags=re.IGNORECASE)
        enforced = [enforce_jurisdiction_sql_single(b.strip(), state) for b in branches if b.strip()]
        return delimiter.join(enforced)
    return enforce_jurisdiction_sql_single(sql, state)

def validate_sql_node(state: GraphState) -> GraphState:
    print("[validate_sql] Validating SQL in sandbox...")
    sql = state["generated_sql"]
    
    if sql == "UNSUPPORTED":
        return {**state, "error_message": "Unsupported query"}
    if sql == "UNAUTHORIZED_DIOCESE":
        return {**state, "error_message": "Unauthorized diocese access"}
    if sql == "UNAUTHORIZED_PARISH":
        return {**state, "error_message": "Unauthorized parish access"}

    # Automatically repair unescaped single quotes in parish names (e.g. 'St. Joseph's Parish' -> 'St. Joseph''s Parish')
    user_parish = state.get("user_parish") or ""
    if user_parish and "'" in user_parish:
        raw_literal = f"'{user_parish}'"
        esc_literal = sql_quote_str(user_parish)
        if raw_literal in sql:
            sql = sql.replace(raw_literal, esc_literal)

    # Deterministically enforce role & scope ID filtering
    sql = enforce_jurisdiction_sql(sql, state)

    # Automatically sanitize and polish select clause to ensure meaningful columns
    sql = sanitize_select_clause(sql, state["question"])
    state = {**state, "generated_sql": sql}


    # Basic safety checks
    sql_upper = sql.upper().strip()
    if not sql_upper.startswith("SELECT"):
        return {**state, "error_message": "Only SELECT queries are allowed."}
        
    for forbidden in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "REPLACE", "CREATE"]:
        if re.search(r'\b' + forbidden + r'\b', sql_upper):
            return {**state, "error_message": f"Query contains forbidden keyword: {forbidden}"}

    clean_sql = re.sub(r'COUNT\s*\(\s*\*\s*\)', '', sql_upper)
    if '*' in clean_sql:
        return {**state, "error_message": "Do not use wildcard SELECT * or f.*. You MUST explicitly select up to 5 human-readable columns (like first_name, last_name, date, etc.) that directly answer the query."}

    if ("PLACE_OF_BIRTH" in sql_upper or "BIRTH_PLACE" in sql_upper) and "BCC" in sql_upper:
        return {**state, "error_message": "Do not filter place_of_birth or birth_place by BCC names. Place of birth represents a town or city, not a Basic Christian Community (BCC). Filter by parish_bcc_id in tabFamily instead."}

    # Check for invalid mix of COUNT(*) and columns without GROUP BY (ignore UNION queries)
    if "UNION" not in sql_upper:
        select_part = sql_upper.split("FROM")[0] if "FROM" in sql_upper else sql_upper
        if re.search(r'COUNT\s*\(\s*\*\s*\)', select_part) and "," in select_part and "GROUP BY" not in sql_upper:
            return {**state, "error_message": "Do not mix COUNT(*) with individual columns in the SELECT clause without a GROUP BY. If the user wants a list of items, do not use COUNT(*). If they want a count, only select COUNT(*)."}



    # EXPLAIN Sandbox check in Frappe MariaDB
    import frappe
    try:
        # Run EXPLAIN to validate syntax and table access
        explain_sql = f"EXPLAIN {sql}"
        frappe.db.sql(explain_sql)
        print("[validate_sql] SQL validated successfully.")
        return {**state, "error_message": ""}
    except Exception as e:
        error_msg = str(e)
        print(f"[validate_sql] SQL Validation Failed: {error_msg}")
        return {**state, "error_message": error_msg}

SQL_REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a SQL rewrite assistant for a MariaDB database in KOINONIA Parish Assistant.
The SQL query you generated failed with a database error.
Rewrite the SQL query to fix the error.

User Question:
{question}

Table Schemas:
{relevant_tables}

Relevant Fields (Semantic matching columns that exist in the tables):
{relevant_fields}

CRITICAL RULES:
1. Fix the syntax or column error reported.
2. Only use columns defined in the table schemas above. Do NOT invent columns.
3. For tabFamily, DO NOT select `first_name`, `last_name`, or `family_id` (those columns only exist in tabMember).
4. NEVER return SELECT * or SELECT alias.* or select unhelpful database system columns (such as `name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`, `idx`, `amended_from`, `_user_tags`, `_comments`, `_assign`, `_liked_by`, `custom`). You MUST explicitly select up to 5 specific, human-readable, helpful columns (like names, key dates, places, status, and IDs).
5. Return ONLY the corrected SQL query — no explanation, no markdown.
6. When the query mentions a "BCC" (e.g. 'Lourdu Matha BCC', 'Christ the King BCC'), ALWAYS filter by the `parish_bcc_id` column in `tabFamily`. NEVER use `place_of_birth` or other birth-related columns to filter by BCC name.
7. If the database error states "Do not mix COUNT(*) with individual columns...", you MUST fix this by removing COUNT(*) entirely from the SELECT clause to return a list of items (since the user asked to "list them"), rather than keeping it.
8. If the user asked for a chart or graph, ALWAYS return exactly TWO columns: one label column and one numeric count column (e.g., `SELECT gender, COUNT(*) FROM tabBaptism GROUP BY gender`). NEVER use pivoted conditional counts like `COUNT(CASE...)`.
"""),
    ("human", """Failed SQL: {failed_sql}
Database Error: {error_message}"""),
])

def rewrite_sql_node(state: GraphState) -> GraphState:
    print(f"[rewrite_sql] Rewriting SQL. Retry count: {state.get('retry_count', 0) + 1}...")
    retry = state.get("retry_count", 0) + 1
    
    response = invoke_llm_with_rotation([
        ("system", SQL_REWRITE_PROMPT.format(
            question=state["question"],
            relevant_tables="\n\n".join(state["relevant_tables"]),
            relevant_fields="\n".join(state["relevant_fields"]),
            failed_sql=state["generated_sql"],
            error_message=state["error_message"]
        ))
    ])
    raw_sql = response.content.strip().strip("```sql").strip("```").strip()
    
    # Strip any markdown code formatting
    if raw_sql.startswith("```"):
        raw_sql = re.sub(r"^```[a-zA-Z]*\n", "", raw_sql)
        raw_sql = re.sub(r"\n```$", "", raw_sql)
        
    return {**state, "generated_sql": raw_sql, "retry_count": retry}

def execute_sql_node(state: GraphState) -> GraphState:
    print("[execute_sql] Running SQL against MariaDB...")
    sql = state["generated_sql"]
    
    if sql in ["UNSUPPORTED", "UNAUTHORIZED_DIOCESE", "UNAUTHORIZED_PARISH"]:
        return {**state, "sql_result": None, "error_message": ""}
        
    import frappe
    try:
        results = frappe.db.sql(sql, as_dict=True)
        print(f"[execute_sql] Query returned {len(results)} rows.")
        return {**state, "sql_result": results, "error_message": ""}
    except Exception as e:
        print(f"[execute_sql] Execution failed: {e}")
        return {**state, "error_message": f"Database execution error: {str(e)}"}

def format_response_node(state: GraphState) -> GraphState:
    print("[format_response] Formatting final response locally...")
    
    if state.get("error_message") == "Unauthorized parish access" or state.get("generated_sql") == "UNAUTHORIZED_PARISH":
        user_role = state.get("user_role") or "User"
        user_parish = state.get("user_parish") or "your assigned parish"
        user_vicariate = state.get("user_vicariate") or "your vicariate"
        user_parishes = state.get("user_parishes") or []
        
        if user_role == "Parish Priest":
            ans = (
                f"🔒 **Access Restricted**\n\n"
                f"As the **Parish Priest** of **{user_parish}**, your jurisdiction and access are strictly limited to records within **{user_parish}**.\n\n"
                f"You do not have permission to view or query member and sacrament registries belonging to other parishes."
            )
        else:
            p_str = ", ".join([f"**{p}**" for p in user_parishes]) if user_parishes else f"**{user_parish}**"
            ans = (
                f"🔒 **Access Restricted**\n\n"
                f"As the **{user_role}** for **{user_vicariate}**, your administration and registry access are strictly limited to your controlled parishes: {p_str}.\n\n"
                f"You do not have permission to view or query registries belonging to parishes outside your jurisdiction."
            )
        return {**state, "final_answer": ans}

    if state.get("error_message") == "Unauthorized diocese access" or state.get("generated_sql") == "UNAUTHORIZED_DIOCESE":
        user_role = state.get("user_role", "Parish Priest")
        user_diocese = state.get("user_diocese") or "your assigned diocese"
        user_parish = state.get("user_parish") or "your assigned parish"
        user_vicariate = state.get("user_vicariate") or "your assigned vicariate"
        foreign_p = state.get("requested_foreign_parish")
        foreign_d = state.get("requested_foreign_diocese")
        
        p_prefix = f"• **{foreign_p}** belongs to the **{foreign_d} Diocese**.\n" if (foreign_p and foreign_d) else (f"• The requested registry belongs to the **{foreign_d} Diocese**.\n" if foreign_d else "")
        
        if user_role == "Bishop":
            ans = (
                f"🔒 **Access Restricted**\n\n"
                f"{p_prefix}"
                f"• As the **Bishop** of **{user_diocese} Diocese**, your jurisdiction and access are strictly limited to records within **{user_diocese} Diocese**.\n\n"
                f"You do not have permission to view or query registries belonging to other dioceses."
            )
        elif user_role == "Parish Priest":
            ans = (
                f"🔒 **Access Restricted**\n\n"
                f"{p_prefix}"
                f"• As a **Parish Priest** for **{user_parish}**, your access is restricted to records within your assigned parish. "
                f"You do not have permission to view data across all parishes in the diocese or other dioceses.\n\n"
                f"If you require diocese-wide reports or statistics, please request them from the Bishop's Office."
            )
        elif user_role in ["Vicar Forane", "Vicar General"]:
            user_parishes = state.get("user_parishes") or []
            p_str = ", ".join([f"**{p}**" for p in user_parishes]) if user_parishes else "your assigned parishes"
            ans = (
                f"🔒 **Access Restricted**\n\n"
                f"{p_prefix}"
                f"• As the **{user_role}** for **{user_vicariate}**, your access is restricted to your assigned parishes ({p_str}) within **{user_diocese} Diocese**.\n\n"
                f"You do not have permission to view records for the entire diocese or other dioceses."
            )
        else:
            ans = (
                f"🔒 **Access Restricted**\n\n"
                f"{p_prefix}"
                f"• Your account role (**{user_role}**) is restricted to local parish records. "
                f"You do not have permission to view data across other parishes or dioceses."
            )
        return {**state, "final_answer": ans}

    if state.get("error_message") == "Unsupported query" or state.get("generated_sql") == "UNSUPPORTED":
        ans = (
            "I'm sorry, but I can only search sacrament registers (Baptism, Communion, Confirmation, Marriage, Anointing of the Sick, and Death) and parish Family/Member registers. "
            "Please ask a question related to these registries, and I'll be happy to search for you! 😊"
        )
        return {**state, "final_answer": ans}
        
    if state.get("error_message"):
        ans = (
            "🙏 I couldn't complete this query right now. "
            "Please try rephrasing your question or ask again in a moment! 😊"
        )
        return {**state, "final_answer": ans}

    raw_results = state["sql_result"]
    
    if not raw_results:
        # Check if the user was querying a parish that exists in another diocese
        import frappe
        foreign_p = None
        foreign_d = None
        user_dio = (state.get("user_diocese") or "").strip()
        user_role_val = state.get("user_role") or "Bishop"
        q_text = (state.get("query_text") or "").lower()
        if frappe.db.table_exists("Parish"):
            all_parishes = frappe.db.sql("SELECT name, diocese_id FROM tabParish", as_dict=True)
            for p in all_parishes:
                p_name = p.get("name") or ""
                p_dio = p.get("diocese_id") or ""
                short_p = p_name.replace("Parish", "").replace("Church", "").replace("Cathedral", "").replace("Shrine", "").strip()
                if short_p and len(short_p) > 3 and re.search(r'\b' + re.escape(short_p.lower()) + r'\b', q_text):
                    if user_dio and p_dio and p_dio.lower() != user_dio.lower():
                        foreign_p = p_name
                        foreign_d = p_dio
                        break
        
        if foreign_p and foreign_d:
            ans = (
                f"🔒 **Access Restricted**\n\n"
                f"• **{foreign_p}** belongs to the **{foreign_d} Diocese**.\n"
                f"• As the **{user_role_val}** of **{user_dio} Diocese**, your jurisdiction and access are strictly limited to records within **{user_dio} Diocese**.\n\n"
                f"You do not have permission to view or query registries belonging to other dioceses."
            )
            return {**state, "final_answer": ans}
            
        q_orig = state.get("question") or ""
        is_tam = bool(re.search(r'[\u0B80-\u0BFF]', q_orig)) or any(kw in q_orig.lower() for kw in ["tamil", "தமிழில்", "தமிழ்"])
        
        gen_sql = state.get("generated_sql") or ""
        
        # Check if query was searching for a specific person's name
        name_search_match = re.search(r"(?:first_name|last_name|bridegroom_name|bride_name|bridegroom_last_name|bride_last_name|full_name|mrg_minister|mrg_register_ref)\s+LIKE\s+'%([^%']+)%'", gen_sql, re.IGNORECASE)
        if name_search_match:
            searched_name = name_search_match.group(1).strip()
            table_match = re.search(r'FROM\s+`?(tab(?:Anointing Of Sick|[A-Za-z0-9_]+))`?', gen_sql, re.IGNORECASE)
            tname = table_match.group(1).strip('`') if table_match else "tabMember"
            reg_name = {
                "tabMarriage": "திருமணப் பதிவேட்டில்",
                "tabBaptism": "ஞானஸ்நானப் பதிவேட்டில்",
                "tabCommunion": "புது நன்மைப் பதிவேட்டில்",
                "tabConfirmation": "உறுதிப்பூசுதல் பதிவேட்டில்",
                "tabDeath": "மரணப் பதிவேட்டில்",
                "tabMember": "உறுப்பினர் பட்டியலில்"
            }.get(tname, "பதிவேட்டில்")
            
            if is_tam:
                ans = f"{reg_name} **{searched_name}** என்ற பெயரில் எந்தப் பதிவும் கண்டறியப்படவில்லை."
            else:
                ans = f"No records found for **{searched_name}** in the registry."
            return {**state, "final_answer": ans}

        # Check if query searched for 2026 / current year on a registry with prior records
        table_match = re.search(r'FROM\s+`?(tab(?:Anointing Of Sick|[A-Za-z0-9_]+))`?', gen_sql, re.IGNORECASE)
        latest_yr = None
        if table_match and any(k in gen_sql for k in ["YEAR(CURDATE())", "2026", "YEAR("]):
            tname = table_match.group(1).strip().strip('`')
            doc_type = tname.replace("tab", "", 1) if tname.startswith("tab") else tname
            if frappe.db.table_exists(doc_type):
                cols = frappe.db.get_table_columns(doc_type)
                date_cols = [c for c in ["death_date", "bapt_date", "mrg_date", "fhc_date", "cnf_date", "anointing_date"] if c in cols]
                if date_cols:
                    dcol = date_cols[0]
                    dio_val = (state.get("user_diocese") or "").strip()
                    dio_cond = f"WHERE diocese_id = '{dio_val}' AND {dcol} IS NOT NULL" if dio_val and "diocese_id" in cols else f"WHERE {dcol} IS NOT NULL"
                    res_max = frappe.db.sql(f"SELECT MAX(YEAR({dcol})) AS max_yr, COUNT(*) AS count_max FROM `{tname}` {dio_cond}", as_dict=True)
                    if res_max and res_max[0].get("max_yr"):
                        latest_yr = res_max[0]["max_yr"]
        
        if latest_yr and latest_yr < 2026:
            if is_tam:
                ans = f"நடப்பு 2026-ஆம் ஆண்டிற்கான பதிவுகள் எதுவும் பதிவேற்றப்படவில்லை. மிக சமீபத்திய பதிவுகள் **{latest_yr}**-ஆம் ஆண்டிற்குரியவை. நீங்கள் **{latest_yr}**-ஆம் ஆண்டின் பதிவுகளைப் பார்க்க விரும்புகிறீர்களா?"
            else:
                ans = f"No records have been recorded for 2026 yet. The latest available records in the registry are from **{latest_yr}**. Would you like to view records for {latest_yr}?"
            suggested_qs = [
                f"{latest_yr}-ல் எத்தனை நபர்கள் இறந்தார்கள்?",
                f"Show {latest_yr} records",
                f"{latest_yr} பதிவுகள்"
            ]
            return {**state, "final_answer": ans, "suggested_questions": suggested_qs}
            
        ans = "உங்கள் தேடலுக்குரிய பதிவுகள் எதுவும் கிடைக்கவில்லை." if is_tam else "No records were found matching your search." 
    else:
        # Keep all results for full interactive table pagination in UI
            
        if isinstance(raw_results, list) and len(raw_results) > 0 and isinstance(raw_results[0], dict):
            # Check for relationship inquiry between two persons
            is_rel_query = (
                "rel_relationship_id" in raw_results[0] or 
                "rel1" in raw_results[0] or
                "relationship1" in raw_results[0] or
                "person1_role" in raw_results[0] or
                "person1_relationship" in raw_results[0] or
                "person2_relationship" in raw_results[0] or
                "rel_first_name" in raw_results[0] or
                "first_name2" in raw_results[0] or
                "person2_first" in raw_results[0] or
                ("relationship_id" in raw_results[0] and len(raw_results[0]) <= 8 and any(k in raw_results[0] for k in ["parish1", "person1", "rel2", "rel_parish_id", "first_name1"]))
            )
            if is_rel_query:
                row = raw_results[0]
                p1_parts = [row.get("person1_fullname") or row.get("first_name") or row.get("person1_first") or row.get("first_name1") or row.get("person1"), row.get("middle_name") or row.get("middle_name1") if not row.get("person1_fullname") else None, row.get("last_name") or row.get("person1_last") or row.get("last_name1") if not row.get("person1_fullname") else None]
                p1 = row.get("person1_fullname") or " ".join([str(p).strip() for p in p1_parts if p and str(p).strip() not in ("", "None", "null", "NULL")]).strip()
                r1 = row.get("relationship_id") or row.get("person1_role") or row.get("person1_relationship") or row.get("relationship1") or row.get("rel1") or "Member"
                parish1 = row.get("parish_id") or row.get("person1_parish") or row.get("parish_name") or row.get("parish1") or ""
                
                p2_parts = [row.get("person2_fullname") or row.get("rel_first_name") or row.get("person2_first") or row.get("first_name2") or row.get("person2"), row.get("rel_middle_name") or row.get("middle_name2") if not row.get("person2_fullname") else None, row.get("rel_last_name") or row.get("person2_last") or row.get("last_name2") if not row.get("person2_fullname") else None]
                p2 = row.get("person2_fullname") or " ".join([str(p).strip() for p in p2_parts if p and str(p).strip() not in ("", "None", "null", "NULL")]).strip()
                r2 = row.get("rel_relationship_id") or row.get("person2_role") or row.get("person2_relationship") or row.get("relationship2") or row.get("rel2") or "Member"
                parish2 = row.get("rel_parish_id") or row.get("person2_parish") or row.get("parish2") or parish1
                
                fam = row.get("family_id") or ""
                dio = row.get("diocese_id") or ""
                
                # Compute natural relationship description
                r1_clean = str(r1).strip().title()
                r2_clean = str(r2).strip().title()
                
                if (r1_clean in ["Father", "Head", "Head Of Family"] and r2_clean in ["Mother", "Spouse", "Wife"]) or (r2_clean in ["Father", "Head", "Head Of Family"] and r1_clean in ["Mother", "Spouse", "Wife"]):
                    rel_sentence = f"**{p1}** and **{p2}** are **Husband & Wife** (Father and Mother of the family)."
                elif r1_clean in ["Father", "Mother"] and r2_clean in ["Son", "Daughter", "Child"]:
                    rel_sentence = f"**{p1}** is the **{r1_clean}** of **{p2}** ({r2_clean})."
                elif r2_clean in ["Father", "Mother"] and r1_clean in ["Son", "Daughter", "Child"]:
                    rel_sentence = f"**{p2}** is the **{r2_clean}** of **{p1}** ({r1_clean})."
                elif r1_clean in ["Son", "Brother", "Daughter", "Sister"] and r2_clean in ["Son", "Daughter", "Sister", "Brother"]:
                    rel_sentence = f"**{p1}** and **{p2}** are **Siblings / Brother & Sister**."
                else:
                    rel_sentence = f"**{p1}** ({r1_clean}) and **{p2}** ({r2_clean}) belong to the same household."
                
                ans = f"👤 **Family Relationship Found**\n\n• {rel_sentence}\n"
                if parish1:
                    ans += f"• **Parish:** {parish1}\n"
                if fam:
                    ans += f"• **Family Registration:** {fam}\n"
                if dio:
                    ans += f"• **Diocese:** {dio} Diocese\n"
                return {**state, "final_answer": ans}

            # Check for Parish Profile & History
            is_parish_profile = len(raw_results) == 1 and any(k in raw_results[0] for k in ["patron_saint", "feast_day", "assistant_priest", "note"]) and any(k in (state.get("question") or "").lower() for k in ["profile", "history", "about", "priest", "saint", "feast", "church"])
            if is_parish_profile:
                row = raw_results[0]
                p_name = row.get("parish_name") or row.get("name") or "Parish"
                p_priest = row.get("parish_priest") or ""
                asst_priest = row.get("assistant_priest") or ""
                saint = row.get("patron_saint") or ""
                feast_val = row.get("feast_day")
                feast = feast_val.strftime("%B %d") if hasattr(feast_val, "strftime") else (str(feast_val) if feast_val else "")
                est_val = row.get("established_date")
                est = est_val.strftime("%B %d, %Y") if hasattr(est_val, "strftime") else (str(est_val) if est_val else "")
                city = row.get("city") or ""
                note = row.get("note") or row.get("history") or ""
                
                if not note or not saint or not p_priest:
                    import frappe
                    p_db = frappe.db.sql("SELECT parish_name, patron_saint, feast_day, established_date, parish_priest, assistant_priest, city, note FROM tabParish WHERE name = %s OR parish_name = %s LIMIT 1", (p_name, p_name), as_dict=True)
                    if p_db:
                        pdb_row = p_db[0]
                        p_name = pdb_row.get("parish_name") or p_name
                        saint = saint or pdb_row.get("patron_saint") or "Patron Saint"
                        p_priest = p_priest or pdb_row.get("parish_priest") or "Parish Priest"
                        asst_priest = asst_priest or pdb_row.get("assistant_priest") or ""
                        if not feast and pdb_row.get("feast_day"):
                            fd = pdb_row["feast_day"]
                            feast = fd.strftime("%B %d") if hasattr(fd, "strftime") else str(fd)
                        if not est and pdb_row.get("established_date"):
                            ed = pdb_row["established_date"]
                            est = ed.strftime("%B %d, %Y") if hasattr(ed, "strftime") else str(ed)
                        city = city or pdb_row.get("city") or ""
                        note = note or pdb_row.get("note") or ""
                
                ans = f"⛪ **{p_name} Profile**\n\n"
                if saint: ans += f"• **Patron Saint:** {saint}\n"
                if feast: ans += f"• **Feast Day:** {feast}\n"
                if est: ans += f"• **Established:** {est}\n"
                if p_priest: ans += f"• **Parish Priest:** {p_priest}\n"
                if asst_priest: ans += f"• **Assistant Priest:** {asst_priest}\n"
                if city: ans += f"• **Location:** {city}\n\n"
                if note:
                    ans += f"📖 **History & Heritage:**\n{note}\n"
                return {**state, "final_answer": ans}

            # Check for Diocese Profile (only when a single diocese is requested)
            is_single_diocese_profile = len(raw_results) == 1 and any(k in raw_results[0] for k in ["diocese_name", "bishop_name"]) and any(k in (state.get("question") or "").lower() for k in ["tell", "about", "profile", "history", "bishop", "chancery", "who is"])
            if is_single_diocese_profile:
                row = raw_results[0]
                d_name = row.get("diocese_name") or row.get("name") or "Diocese"
                b_name = row.get("bishop_name") or "Bishop / Ordinary"
                est_val = row.get("established_date")
                est = est_val.strftime("%B %d, %Y") if hasattr(est_val, "strftime") else (str(est_val) if est_val else "Historic")
                addr = row.get("address") or row.get("city") or "Bishop's House"
                phone = row.get("phone") or ""
                email = row.get("email") or ""
                web = row.get("website") or ""
                note = row.get("note") or row.get("history") or ""
                
                if not note:
                    import frappe
                    d_db = frappe.db.sql("SELECT diocese_name, bishop_name, established_date, city, phone, email, website, note FROM tabDiocese WHERE name = %s OR diocese_name = %s LIMIT 1", (d_name, d_name), as_dict=True)
                    if d_db:
                        ddb_row = d_db[0]
                        d_name = ddb_row.get("diocese_name") or d_name
                        b_name = ddb_row.get("bishop_name") or b_name
                        if not est_val and ddb_row.get("established_date"):
                            ed = ddb_row["established_date"]
                            est = ed.strftime("%B %d, %Y") if hasattr(ed, "strftime") else str(ed)
                        addr = ddb_row.get("city") or addr
                        phone = phone or ddb_row.get("phone") or ""
                        email = email or ddb_row.get("email") or ""
                        web = web or ddb_row.get("website") or ""
                        note = ddb_row.get("note") or ""
                
                contacts = []
                if phone: contacts.append(f"📞 **Phone:** {phone}")
                if email: contacts.append(f"✉️ **Email:** {email}")
                if web: contacts.append(f"🌐 **Website:** [{web}]({web if web.startswith('http') else 'https://' + web})")
                contact_str = " | ".join(contacts) if contacts else ""
                
                ans = f"🏛️ **{d_name} Profile**\n\n• **Bishop / Ordinary:** {b_name}\n• **Established:** {est}\n• **Chancery / City:** {addr}\n"
                if contact_str:
                    ans += f"• **Contact:** {contact_str}\n\n"
                if note:
                    ans += f"📖 **History & Heritage:**\n{note}\n"
                return {**state, "final_answer": ans}

            # Compute full_name if first_name / last_name are present
            has_name_fields = any(k in raw_results[0] for k in ["first_name", "last_name", "bridegroom_name", "bride_name"])
            if has_name_fields:
                for row in raw_results:
                    if "full_name" not in row:
                        parts = [
                            row.get("first_name") or row.get("bridegroom_name") or row.get("bride_name"),
                            row.get("middle_name") or row.get("bridegroom_middle_name") or row.get("bride_middle_name"),
                            row.get("last_name") or row.get("bridegroom_last_name") or row.get("bride_last_name")
                        ]
                        fn_str = " ".join([str(p).strip() for p in parts if p and str(p).strip() not in ("", "None", "null", "NULL")]).strip()
                        if fn_str:
                            row["full_name"] = fn_str

            raw_headers = list(raw_results[0].keys())
            
            # Define system metadata and unhelpful fields to exclude if other columns are present
            system_fields = {
                'name', 'creation', 'modified', 'modified_by', 'owner', 'docstatus', 'idx',
                '_user_tags', '_comments', '_assign', '_liked_by', 'amended_from', 'custom', 'active'
            }
            
            # Filter headers
            headers = [h for h in raw_headers if h.lower() not in system_fields]
            if not headers:
                headers = raw_headers
                
            # If full_name is present, prioritize it and remove fragmented first/middle/last from wide table
            if "full_name" in headers and len(headers) > 3:
                headers = ["full_name"] + [h for h in headers if h.lower() not in ["full_name", "first_name", "middle_name", "last_name"]]
                
            # Define priority ordering weights for common meaningful fields (lower weight = higher priority)
            field_weights = {
                # Names
                'full_name': 0, 'first_name': 1, 'middle_name': 2, 'last_name': 3,
                'diocese_name': 1, 'vicariate_name': 1, 'parish_name': 1, 'family_name': 1,
                'bishop_name': 2, 'vicar_forane': 2, 'parish_priest': 2, 'family_head': 2,
                'bridegroom_name': 1, 'bride_name': 2, 'witness1_name': 4, 'witness2_name': 5,
                
                # Codes & IDs
                'diocese_code': 10, 'vicariate_code': 10, 'parish_code': 10, 'family_card_no': 10,
                'diocese_id': 11, 'vicariate_id': 12, 'parish_id': 13, 'family_id': 14, 'member_id': 15,
                
                # Dates
                'established_date': 20, 'bapt_date': 21, 'mrg_date': 22, 'cnf_date': 23, 'fhc_date': 24, 'death_date': 25,
                'dob': 26, 'age': 27, 'established': 28,
                
                # Places
                'bapt_place': 30, 'birth_place': 31, 'place_of_birth': 32, 'city': 33, 'state_id': 34, 'country_id': 35,
                
                # Classifications/Groupings
                'status': 40, 'living_status': 41, 'marital_status_id': 42,
                'parish_bcc_id': 43, 'zone_id': 44
            }
            
            # Sort headers by weight, keeping stable ordering for others
            headers.sort(key=lambda h: field_weights.get(h.lower(), 100))
            
            # Format 1: Single Row, Single Column
            if len(raw_results) == 1 and len(headers) == 1:
                k = headers[0]
                v = raw_results[0].get(k)
                label = str(k).replace("_", " ").title().replace("Count(*)", "Total Count").replace("Count(Idx)", "Total Count")
                ans = f"**{label}**: {v}"
                
            # Format 2: Single Row, Multiple Columns
            elif len(raw_results) == 1 and len(headers) > 1:
                # Try to fetch full document details if possible to display all fields
                table_match = re.search(r'FROM\s+`?(tab[A-Za-z0-9_ ]+)`?', state.get("generated_sql", ""), re.IGNORECASE)
                doc_detail_card = None
                if table_match:
                    table_name = table_match.group(1).strip().strip('`')
                    doctype_name = table_name.replace("tab", "", 1) if table_name.startswith("tab") else table_name
                    if doctype_name == "Anointing Of Sick":
                        doctype_name = "Anointing Of Sick"
                    
                    doc_id = raw_results[0].get("name")
                    if doc_id:
                        try:
                            import frappe
                            import datetime
                            doc = frappe.get_doc(doctype_name, doc_id)
                            meta = frappe.get_meta(doctype_name)
                            
                            # Gather meaningful fields
                            fields_data = []
                            fields_data.append((meta.title_field or "ID", doc_id))
                            
                            system_fields = {
                                'name', 'creation', 'modified', 'modified_by', 'owner', 'docstatus', 'idx',
                                '_user_tags', '_comments', '_assign', '_liked_by', 'amended_from', 'custom', 'active'
                            }
                            
                            for df in meta.fields:
                                if df.fieldtype not in ["Section Break", "Column Break", "Table", "Password"]:
                                    val = doc.get(df.fieldname)
                                    if val is not None and str(val).strip() != "" and df.fieldname not in system_fields:
                                        # Format date values nicely
                                        if df.fieldtype == "Date" and isinstance(val, datetime.date):
                                             val = val.strftime("%d-%b-%Y")
                                        elif df.fieldtype == "Check":
                                            val = "Yes" if val else "No"
                                        fields_data.append((df.label or df.fieldname.replace("_", " ").title(), val))
                                        
                            doc_detail_card = f"### 📋 {doctype_name} Details: {doc_id}\n\n"
                            doc_detail_card += "\n".join(f"- **{label}**: {val}" for label, val in fields_data)
                        except Exception as e:
                            print(f"[format_response] Failed to fetch full doc details: {e}")
                            
                if doc_detail_card:
                    ans = doc_detail_card
                else:
                    ans = ""
                    for k in headers:
                        v = raw_results[0].get(k)
                        if v is None or str(v).strip() in ("", "None", "null", "NULL", "undefined"):
                            v = "-"
                        label = str(k).replace("_", " ").title()
                        ans += f"- **{label}**: {v}\n"
                    
            # Format 3: Multiple Rows (Markdown Table with Disambiguation Context)
            else:
                # Enforce a maximum of 5 columns to prevent UI overflow
                if len(headers) > 5:
                    headers = headers[:5]
                    
                def _fmt_val(v):
                    if v is None or str(v).strip() in ("", "None", "null", "NULL", "undefined"):
                        return "-"
                    return str(v).replace("\n", " ").replace("|", "\\|")

                table_md = "| " + " | ".join(str(h).replace("_", " ").title() for h in headers) + " |\n"
                table_md += "|" + "|".join(["---"] * len(headers)) + "|\n"
                for row in raw_results:
                    table_md += "| " + " | ".join(_fmt_val(row.get(h)) for h in headers) + " |\n"
                
                num_records = len(raw_results)
                q_original = state.get("question") or ""
                is_tamil = bool(re.search(r'[\u0B80-\u0BFF]', q_original)) or any(kw in q_original.lower() for kw in ["tamil", "தமிழில்", "தமிழ்"])
                if is_tamil:
                    header_text = f"உங்கள் தேடலுக்கு ஏற்ப **{num_records}** பதிவுகள் கண்டறியப்பட்டன:\n\n"
                else:
                    header_text = f"Found **{num_records}** records matching your search:\n\n"
                
                # Collect full names for follow-up prompt if available
                names = []
                for row in raw_results:
                    fn_val = row.get("full_name")
                    if not fn_val:
                        parts = [
                            row.get("first_name") or row.get("bridegroom_name") or row.get("bride_name"),
                            row.get("middle_name"),
                            row.get("last_name") or row.get("bridegroom_last_name") or row.get("bride_last_name")
                        ]
                        fn_val = " ".join([str(p).strip() for p in parts if p and str(p).strip() not in ("", "None", "null", "NULL")]).strip()
                    if fn_val and fn_val not in names:
                        names.append(fn_val)
                
                footer_text = ""
                q_user = (state.get("question") or "").lower()
                is_group_or_list_query = any(k in q_user for k in [
                    "children", "child", "members", "families", "all", "list", "show", "who are", "they", "them", "both", "details"
                ])
                if names and 1 < len(names) <= 5 and not is_group_or_list_query:
                    names_str = " or ".join([f"**{n}**" for n in names])
                    footer_text = f"\n💡 *Did you mean {names_str}? Ask again with the full name for a direct match.*"
                
                ans = header_text + table_md + footer_text
                
                
        else:
            ans = str(raw_results)

    # Log successful queries for few-shot learning
    if state.get("history_id") and state.get("history_id") > 0:
        update_correctness_flag(state["history_id"], 1)

    return {**state, "final_answer": ans}

# ─── Define Router Decisions ──────────────────────────────────────────────────

def decide_route(state: GraphState):
    return state["route"]

def decide_validation(state: GraphState):
    if state.get("error_message") in ["Unsupported query", "Unauthorized diocese access", "Unauthorized parish access"]:
        return "unsupported"
    elif state.get("error_message"):
        if state.get("retry_count", 0) < MAX_RETRIES:
            return "retry"
        else:
            return "failed"
    else:
        return "valid"

def decide_execution(state: GraphState):
    if state.get("error_message"):
        if state.get("retry_count", 0) < MAX_RETRIES:
            return "retry"
        else:
            return "failed"
    else:
        return "success"

# ─── Assemble LangGraph Workflow ──────────────────────────────────────────────

def build_graph():
    workflow = StateGraph(GraphState)
    workflow.add_node("router", router_node)
    workflow.add_node("greeting", greeting_node)
    workflow.add_node("unclear", unclear_node)
    workflow.add_node("enhance_query", enhance_query_node)
    workflow.add_node("retrieve_context", retrieve_context_node)
    workflow.add_node("generate_sql", generate_sql_node)
    workflow.add_node("validate_sql", validate_sql_node)
    workflow.add_node("rewrite_sql", rewrite_sql_node)
    workflow.add_node("execute_sql", execute_sql_node)
    workflow.add_node("format_response", format_response_node)
    workflow.set_entry_point("router")
    workflow.add_conditional_edges("router", decide_route, {"greeting": "greeting", "unclear": "unclear", "text_to_sql": "enhance_query"})
    workflow.add_edge("greeting", END)
    workflow.add_edge("unclear", END)
    workflow.add_edge("enhance_query", "retrieve_context")
    workflow.add_edge("retrieve_context", "generate_sql")
    workflow.add_edge("generate_sql", "validate_sql")
    workflow.add_conditional_edges("validate_sql", decide_validation, {"valid": "execute_sql", "retry": "rewrite_sql", "unsupported": "format_response", "failed": "format_response"})
    workflow.add_edge("rewrite_sql", "validate_sql")
    workflow.add_conditional_edges("execute_sql", decide_execution, {"success": "format_response", "retry": "rewrite_sql", "failed": "format_response"})
    workflow.add_edge("format_response", END)
    return workflow.compile()

app = build_graph()

# ─── Public Invocation Entrypoint ──────────────────────────────────────────────

def run_query(question: str, history: list = None, reference_text: str = None, user_role: str = "Parish Priest", user_parish: str = None, user_vicariate: str = None, user_diocese: str = None, user_parishes: list = None, user_member_id: str = None, user_email: str = None, **kwargs) -> dict:
    app = build_graph()
    
    # 1. Embed query to check if it's already in history
    embedding = embed_text(question)
    
    # Log query history to Postgres (initializes thread, correctness_flag defaults to NULL)
    history_id = log_query_history(question, "", embedding)
    
    # 2. Run graph execution
    initial_state = {
        "question": question,
        "history": history or [],
        "reference_text": reference_text or "",
        "route": "",
        "enhanced_query": "",
        "relevant_tables": [],
        "relevant_fields": [],
        "few_shot_examples": "",
        "query_embedding": embedding,
        "generated_sql": "",
        "llm_explanation": "",
        "sql_result": None,
        "error_message": "",
        "retry_count": 0,
        "final_answer": "",
        "history_id": history_id,
        "user_role": user_role,
        "user_parish": user_parish,
        "user_vicariate": user_vicariate,
        "user_diocese": user_diocese,
        "user_parishes": user_parishes or [],
        "user_member_id": user_member_id,
        "user_email": user_email
    }
    
    langsmith_config = {
        "run_name": f"Koinonia_RAG_Pipeline: {question[:40]}",
        "metadata": {
            "user_role": user_role,
            "user_diocese": user_diocese,
            "user_parish": user_parish,
            "question": question
        },
        "tags": [user_role, user_diocese or "Global"]
    }
    
    try:
        final_state = app.invoke(initial_state, config=langsmith_config)
    except Exception as e:
        print(f"[run_query] Graph execution error: {e}")
        return {"reply": "Sorry, I encountered an error while processing your request.", "generated_sql": ""}

    generated_sql = final_state.get("generated_sql", "")
    
    # Update the query history in postgres with the actual generated SQL
    if history_id and generated_sql:
        try:
            import psycopg2
            conn = psycopg2.connect(**PG_CONFIG)
            with conn.cursor() as cur:
                # Only update if the row is not already marked as correct (correctness_flag is not 1)
                cur.execute("UPDATE koinonia_query_history SET generated_sql = %s WHERE id = %s AND (correctness_flag IS NULL OR correctness_flag != 1)", (generated_sql, history_id))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[run_query] Failed to update query history SQL: {e}")

    suggested = final_state.get("suggested_questions") or generate_suggested_questions(
        question, 
        user_role=user_role, 
        user_diocese=user_diocese,
        user_parish=user_parish,
        user_vicariate=user_vicariate
    )
    return {
        "reply": final_state.get("final_answer", ""),
        "generated_sql": generated_sql,
        "sql_result": final_state.get("sql_result"),
        "suggested_questions": suggested
    }


def generate_suggested_questions(
    question: str, 
    user_role: str = "Parish Priest", 
    user_diocese: str = "Salem",
    user_parish: str = None,
    user_vicariate: str = None
) -> list:
    """Generates 3-4 highly relevant contextual follow-up questions using AI strictly answerable from available church database DocTypes and bounded by user's role jurisdiction."""
    if not question or not question.strip():
        return []
    
    parish_info = f"Assigned Parish: {user_parish}" if user_parish else "No single parish assigned"
    vicariate_info = f"Assigned Vicariate: {user_vicariate}" if user_vicariate else ""
    
    try:
        system_instruction = (
            "You are an intelligent Catholic Parish & Diocesan assistant for KOINONIA.\n"
            "Given the user's current query and context, generate 3 to 4 short, clickable FOLLOW-UP SEARCH PROMPTS that the user would want to ask next to explore related church data.\n\n"
            "CRITICAL INSTRUCTION — USER SEARCH PROMPTS ONLY (NEVER ASK QUESTIONS TO THE USER):\n"
            "- Every suggestion MUST be an actionable search query that the USER sends to the assistant (e.g. 'Show top 5 parishes with highest members', 'Compare male vs female members in my diocese', 'Count families in each parish', 'List baptisms in 2024').\n"
            "- NEVER ASK CLARIFICATION QUESTIONS TO THE USER! Never generate questions like 'Which sacrament should be graphed?', 'Specify year range?', 'Do you want all dioceses?', 'Include only active parishes?'. These are strictly forbidden.\n"
            "- Every prompt must be a complete, ready-to-execute user question that searches the database.\n\n"
            f"USER JURISDICTION & ROLE CONTEXT:\n"
            f"- User Role: {user_role}\n"
            f"- Diocese: {user_diocese or 'Not specified'}\n"
            f"- {parish_info}\n"
            f"- {vicariate_info}\n\n"
            "STRICT ROLE-BASED ACCESS LIMITS (Crucial: NEVER suggest questions outside the user's jurisdiction):\n"
            "1. If User Role is 'Parish Priest':\n"
            "   - The questions MUST be strictly scoped to their own parish ('in my parish').\n"
            "   - Allowed: 'Count baptisms in my parish for 2024', 'Show families in my parish', 'Total members in my parish'.\n"
            "   - FORBIDDEN: NEVER suggest diocese-wide census or searching other parishes.\n"
            "2. If User Role is 'Vicar Forane' or 'Vicar General':\n"
            "   - The questions MUST be scoped to their vicariate or controlled parishes ('in my vicariate', 'across parishes in my vicariate').\n"
            "3. If User Role is 'Bishop', 'Chancellor', 'Curia', or 'Administrator':\n"
            "   - The questions can be diocese-wide ('in my diocese', 'across parishes in diocese').\n"
            "4. If User Role is 'Parishioner' or 'Member':\n"
            "   - The questions MUST be personal/family scoped ('Show my family details', 'Parish patron saint').\n\n"
            "STRICT DATABASE SCHEMA BOUNDARIES (You must ONLY suggest questions answerable from these 9 active DocTypes):\n"
            "1. Parish & Diocesan Directory (DocTypes: tabDiocese, tabVicariate, tabParish)\n"
            "2. Family & Parishioner Census (DocTypes: tabFamily, tabMember)\n"
            "3. Sacramental Registers (DocTypes: tabBaptism, tabCommunion, tabConfirmation, tabMarriage, tabDeath)\n\n"
            "FORBIDDEN TOPICS (NEVER suggest these because NO data exists in the database for them):\n"
            "- DO NOT suggest events, diocesan events, parish feasts, calendar schedules, or mass timings.\n"
            "- DO NOT suggest finances, donations, parish budget, collections, or accounts.\n"
            "- DO NOT suggest sermons, homilies, catechism, or clergy transfer orders.\n\n"
            "CRITICAL RULES:\n"
            "1. Return ONLY a valid JSON array of 3 or 4 short question strings.\n"
            "2. Keep each question concise (under 8 words).\n"
            "3. Ensure EVERY question is a direct user query searchable in the database.\n"
            "4. Do NOT output markdown, backticks, or any explanation."
        )
        prompt = [
            ("system", system_instruction),
            ("human", f"User Question: '{question}'")
        ]
        resp = invoke_llm_with_rotation(prompt)
        content = resp.content.strip()
        
        # Robust JSON array extraction
        match = re.search(r"\[\s*.*?\s*\]", content, re.DOTALL)
        if match:
            content = match.group(0)
            
        parsed = json.loads(content)
        if isinstance(parsed, list) and len(parsed) > 0:
            return [str(q).strip().strip('"').strip("'") for q in parsed if str(q).strip()][:4]
    except Exception as e:
        print(f"[generate_suggested_questions] Warning: {e}")
    
    # Fully dynamic fallback using keyword matching and entity extraction with role scoping
    q_low = question.lower()
    
    # Scope determination based on role
    if user_role in ["Bishop", "Chancellor", "Curia", "Administrator", "System Manager"]:
        geo_scope = f"{user_diocese} Diocese" if user_diocese else "my diocese"
    elif user_role in ["Vicar Forane", "Vicar General"]:
        geo_scope = "my vicariate"
    else:
        geo_scope = f"{user_parish}" if user_parish else "my parish"
    
    # 1. Parse Year
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", q_low)
    year = year_match.group(0) if year_match else "2026"
    prev_year = str(int(year) - 1) if year.isdigit() else "2025"
    
    # 2. Parse Sacrament
    sacraments = ["baptism", "marriage", "communion", "confirmation", "death", "sacrament"]
    sacrament = "sacrament"
    for s in sacraments:
        if s in q_low:
            sacrament = s
            break
            
    # 3. Dynamic Fallbacks
    if sacrament != "sacrament":
        return [
            f"Breakdown {sacrament}s by month in {geo_scope} for {year}",
            f"Compare {year} {sacrament}s with {prev_year} in {geo_scope}",
            f"Give this {sacrament} record in graph",
            f"List {sacrament}s with parents names in {geo_scope}"
        ]
        
    if "family" in q_low or "member" in q_low:
        names = re.findall(r"\b[A-Z][a-z]+\b", question)
        name_str = f" for {names[0]}" if names else ""
        return [
            f"Show family registration details{name_str}",
            f"Count members by gender in {geo_scope}",
            f"Show families by BCC unit in {geo_scope}",
            "Who is the family head?"
        ]
        
    if "diocese" in q_low or "parish" in q_low or "vicariate" in q_low:
        if user_role in ["Bishop", "Chancellor", "Curia", "Administrator", "System Manager"]:
            return [
                f"List all parishes in {geo_scope}",
                f"Show total families in each parish of {geo_scope}",
                f"Count members in each parish of {geo_scope}",
                "Compare member counts across dioceses"
            ]
        elif user_role in ["Vicar Forane", "Vicar General"]:
            return [
                "List parishes in my vicariate",
                "Total members in my controlled parishes",
                "Show families in my controlled parishes",
                "Total members in my diocese"
            ]
        else:
            return [
                f"Show families in {geo_scope}",
                f"Total members in {geo_scope}",
                f"Show total counts of all sacraments in {geo_scope}",
                f"List active BCC units in {geo_scope}"
            ]
        
    if user_role in ["Bishop", "Chancellor", "Curia", "Administrator", "System Manager"]:
        return [
            f"Total members in {geo_scope}",
            f"Show total counts of all sacraments in {geo_scope}",
            f"List all parishes in {geo_scope}",
            f"Show total families in each parish of {geo_scope}"
        ]
    elif user_role in ["Vicar Forane", "Vicar General"]:
        return [
            "Total members in my controlled parishes",
            "Show total counts of all sacraments in my vicariate",
            "List parishes in my vicariate",
            "Show families in my parish"
        ]
    else:
        return [
            f"Total members in {geo_scope}",
            f"Show total counts of all sacraments in {geo_scope}",
            f"Show families in {geo_scope}",
            f"Count baptisms in {geo_scope}"
        ]
