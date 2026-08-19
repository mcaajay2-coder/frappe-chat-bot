import os

file_path = r"C:\Users\ajaij\.gemini\antigravity\brain\5a92c275-9ea3-485e-b1b8-0f6b9fed07d0\koinonia_assistant\koinonia_assistant\rag\rag_engine.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Add imports
imports = """import torch
from typing import TypedDict, Any
from dotenv import load_dotenv

from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

_cross_encoder = None
def get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        print("[CrossEncoder] Loading model...")
        _cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    return _cross_encoder"""

content = content.replace("import torch\nfrom typing import TypedDict, Any\nfrom dotenv import load_dotenv", imports)


# Replace fetch_relevant_schemas
old_fetch_schemas = """def fetch_relevant_schemas(original_query: str, enhanced_query: str, query_embedding: list[float], k: int = 2) -> str:
    conn = psycopg2.connect(**PG_CONFIG)
    candidates = []
    seen = set()
    
    combined_query_text = f"{original_query} {enhanced_query}"
    
    try:
        with conn.cursor() as cur:
            # 1. Substring matching for custom tables
            cur.execute("SELECT table_name, schema_ddl FROM koinonia_table_schemas;")
            all_tables = cur.fetchall()
            for tname, ddl in all_tables:
                clean_t = tname.lower()
                if clean_t.startswith("tab"):
                    clean_t = clean_t[3:]
                
                # Support "anointing of sick", "anointing", "sick", "marriage", "baptism", "communion", "confirmation", "death", "member", "family"
                match_keywords = [clean_t, clean_t.replace("_", " ")]
                if any(kw in combined_query_text.lower() for kw in match_keywords):
                    if tname not in seen:
                        seen.add(tname)
                        candidates.append((tname, ddl))

            # 2. Semantic vector search (Priority 2)
            cur.execute(\"\"\"
                SELECT table_name, schema_ddl
                FROM koinonia_table_schemas
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            \"\"\", (query_embedding, k))
            for tname, ddl in cur.fetchall():
                if tname not in seen:
                    seen.add(tname)
                    candidates.append((tname, ddl))
                    
        selected_table_names = rerank_tables(original_query, candidates)
        schema_map = {tname: ddl for tname, ddl in candidates}
        final_results = []
        for tname in selected_table_names:
            if tname in schema_map:
                final_results.append((tname, schema_map[tname]))
                
    finally:
        conn.close()
        
    pruned_results = []
    for tname, ddl in final_results:
        pruned_results.append(f"{tname}:\\n{ddl}")
        
    return pruned_results"""

new_fetch_schemas = """def fetch_relevant_schemas(original_query: str, enhanced_query: str, query_embedding: list[float], k: int = 2) -> str:
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
            
            cur.execute(\"\"\"
                SELECT table_name, schema_ddl
                FROM koinonia_table_schemas
                ORDER BY embedding <=> %s::vector
                LIMIT 5;
            \"\"\", (query_embedding,))
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
    for tname, ddl in final_results:
        pruned_results.append(f"{tname}:\\n{ddl}")
        
    return pruned_results"""

content = content.replace(old_fetch_schemas, new_fetch_schemas)


# Replace fetch_relevant_fields
old_fetch_fields = """def fetch_relevant_fields(query_embedding: list[float], k: int = 3) -> list[str]:
    conn = psycopg2.connect(**PG_CONFIG)
    results = []
    try:
        with conn.cursor() as cur:
            cur.execute(\"\"\"
                SELECT table_name, field_name, field_type, field_label, description,
                       (embedding <=> %s::vector) as distance
                FROM koinonia_field_schemas
                ORDER BY distance ASC
                LIMIT %s;
            \"\"\", (query_embedding, k))
            for row in cur.fetchall():
                results.append(f"- Table `{row[0]}`, Column `{row[1]}` (Type: {row[2]}, Label: {row[3]}): {row[4]}")
    except Exception as e:
        print("[RAG Context] Error fetching relevant fields:", e)
    finally:
        conn.close()
    return results"""

new_fetch_fields = """def fetch_relevant_fields(query_embedding: list[float], combined_query_text: str, k: int = 5) -> list[str]:
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
            
            cur.execute(\"\"\"
                SELECT table_name, field_name, field_type, field_label, description
                FROM koinonia_field_schemas
                ORDER BY embedding <=> %s::vector
                LIMIT 10;
            \"\"\", (query_embedding,))
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
    return results"""

content = content.replace(old_fetch_fields, new_fetch_fields)


# Replace call to fetch_relevant_fields
old_call = """relevant_fields = fetch_relevant_fields(state["query_embedding"])"""
new_call = """relevant_fields = fetch_relevant_fields(state["query_embedding"], combined_query)"""

content = content.replace(old_call, new_call)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
