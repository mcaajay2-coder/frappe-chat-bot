from koinonia_assistant.rag.rag_engine import fetch_relevant_fields, embed_text

def run():
    query = "List families in Lourdu Matha BCC"
    emb = embed_text(query)
    fields = fetch_relevant_fields(emb, query)
    for f in fields:
        print(f)
