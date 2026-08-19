import os
import psycopg2
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '.env'))

PG_CONFIG = {
    "host":     os.getenv("PG_HOST",     "postgres-vector"),
    "port":     int(os.getenv("PG_PORT", 5432)),
    "dbname":   os.getenv("PG_DB",      "parish_vectordb"),
    "user":     os.getenv("PG_USER",    "postgres"),
    "password": os.getenv("PG_PASS",    "password"),
}

def test_fetch_fields():
    print("Loading cross encoder...")
    ce = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    print("Loaded.")

    conn = psycopg2.connect(**PG_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT table_name, field_name, field_type, field_label, description FROM koinonia_field_schemas")
            all_fields = cur.fetchall()
            
            docs = []
            for row in all_fields:
                doc = f"Table: {row[0]}, Column: {row[1]}, Type: {row[2]}, Label: {row[3]}, Desc: {row[4]}"
                docs.append(doc)
            
            tokenized_docs = [doc.lower().split() for doc in docs]
            bm25 = BM25Okapi(tokenized_docs)
            
            query = "baptism 2025 how many ? in infant jesus parish"
            tokenized_query = query.lower().split()
            bm25_scores = bm25.get_scores(tokenized_query)
            
            # Get top 10 from BM25
            top_bm25_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:10]
            
            print(f"Top BM25 results for '{query}':")
            for i in top_bm25_indices:
                print(f"[{bm25_scores[i]:.2f}] {docs[i]}")
                
            # Cross Encoder Reranking
            pairs = [[query, docs[i]] for i in top_bm25_indices]
            ce_scores = ce.predict(pairs)
            
            print("\nCross Encoder Scores:")
            for idx, score in zip(top_bm25_indices, ce_scores):
                print(f"[{score:.2f}] {docs[idx]}")
                
    finally:
        conn.close()

if __name__ == "__main__":
    test_fetch_fields()
