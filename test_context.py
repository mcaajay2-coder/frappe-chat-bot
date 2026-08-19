import frappe
from koinonia_assistant.rag.rag_engine import run_query

frappe.init(site="frontend")
frappe.connect()
result = run_query(
    "list them", 
    history=[{"role": "user", "content": "list marriage 2015 to 2018 how many?"}, {"role": "bot", "content": "**Total Count**: 23"}],
    user_role="Bishop"
)
print("Result:", result)
