import frappe
from koinonia_assistant.rag.rag_engine import enhance_query_node

frappe.init(site="frontend")
frappe.connect()

state = {
    "question": "list them",
    "history": [
        {"role": "user", "content": "list marriage 2015 to 2018 how many?"}, 
        {"role": "bot", "content": "**Total Count**: 23"}
    ]
}
new_state = enhance_query_node(state)
print("Enhanced query:", new_state["enhanced_query"])
