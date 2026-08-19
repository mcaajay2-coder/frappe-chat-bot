import frappe
import os

def after_install():
    """Executed automatically when koinonia_assistant is installed on any Frappe site."""
    print("[Koinonia Assistant] Running post-installation setup...")
    setup_roles()
    setup_workspace()
    setup_vectordb()
    print("[Koinonia Assistant] Installation complete! Ready for use.")

def after_migrate():
    """Executed automatically after bench migrate."""
    print("[Koinonia Assistant] Running post-migration verification...")
    setup_roles()
    setup_workspace()
    setup_vectordb()
    print("[Koinonia Assistant] Migration sync complete.")

def setup_roles():
    """Ensures all 13 hierarchical Catholic diocesan & parish roles exist in the database."""
    roles = [
        "Bishop",
        "Curia",
        "Vicar General",
        "Chancellor",
        "Financial Administrator",
        "Secretary to the Bishop",
        "Vicar Forane",
        "Parish Priest",
        "Commission Director",
        "Institution Head",
        "Staff",
        "Priest",
        "Parishioner"
    ]
    for r in roles:
        if not frappe.db.exists("Role", r):
            role_doc = frappe.new_doc("Role")
            role_doc.role_name = r
            role_doc.desk_access = 1
            role_doc.is_custom = 1
            role_doc.save(ignore_permissions=True)
            print(f"[Koinonia Assistant] Created Role: {r}")
    frappe.db.commit()

def setup_workspace():
    """Creates the public Desk Workspace with link to the Koinonia Chat Assistant interface."""
    roles = [
        "System Manager", "Administrator", "Bishop", "Curia", "Vicar General",
        "Chancellor", "Financial Administrator", "Secretary to the Bishop",
        "Vicar Forane", "Parish Priest", "Commission Director", "Institution Head",
        "Staff", "Priest", "Parishioner"
    ]
    
    if not frappe.db.exists("Workspace", "Koinonia Assistant"):
        ws = frappe.new_doc("Workspace")
        ws.title = "Koinonia Assistant"
        ws.label = "Koinonia Assistant"
        ws.type = "Link"
        ws.link_type = "Page"
        ws.link_to = "koinonia-chat"
        ws.public = 1
        ws.icon = "message-square"
        for r in roles:
            ws.append("roles", {"role": r})
        ws.save(ignore_permissions=True)
        frappe.db.commit()
        print("[Koinonia Assistant] Created public Workspace 'Koinonia Assistant'.")
    else:
        ws = frappe.get_doc("Workspace", "Koinonia Assistant")
        existing = [r.role for r in ws.roles]
        changed = False
        for r in roles:
            if r not in existing:
                ws.append("roles", {"role": r})
                changed = True
        if changed:
            ws.save(ignore_permissions=True)
            frappe.db.commit()
            print("[Koinonia Assistant] Updated Workspace roles.")

def setup_vectordb():
    """Initializes Postgres pgvector tables and runs initial schema ingestion if DB is accessible."""
    try:
        from koinonia_assistant.rag.ingest import setup_database, ingest_all_table_schemas, ingest_field_schemas
        print("[Koinonia Assistant] Initializing Vector DB tables in Postgres...")
        setup_database()
        print("[Koinonia Assistant] Ingesting DocType schemas into Vector DB...")
        ingest_all_table_schemas()
        ingest_field_schemas()
        print("[Koinonia Assistant] Vector DB initialization finished successfully.")
    except Exception as e:
        print(f"[Koinonia Assistant] Vector DB auto-setup skipped or encountered notice: {e}")
