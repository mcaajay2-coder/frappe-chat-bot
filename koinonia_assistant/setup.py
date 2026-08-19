import frappe
import os

DOCTYPES = [
    "Diocese", "Vicariate", "Parish", "Family", "Member",
    "Baptism", "Communion", "Confirmation", "Marriage", "Anointing Of Sick", "Death"
]

ALL_CHURCH_ROLES = [
    "Bishop", "Curia", "Vicar General", "Chancellor", "Financial Administrator",
    "Secretary to the Bishop", "Vicar Forane", "Parish Priest", "Commission Director",
    "Institution Head", "Staff", "Priest", "Parishioner", "Desk User", "System Manager"
]

ADMIN_ROLES = ["Bishop", "Vicar General", "Chancellor", "System Manager", "Administrator"]
WRITE_ROLES = ["Bishop", "Vicar General", "Chancellor", "Parish Priest", "Staff", "System Manager", "Administrator"]
READ_ONLY_ROLES = ["Curia", "Vicar Forane", "Commission Director", "Institution Head", "Priest", "Parishioner", "Desk User"]

def after_install():
    """Executed automatically when koinonia_assistant is installed on any Frappe site."""
    print("[Koinonia Assistant] Running post-installation setup...")
    setup_roles()
    setup_workspaces()
    setup_docperms()
    setup_vectordb()
    print("[Koinonia Assistant] Installation complete! All permissions & icons configured.")

def after_migrate():
    """Executed automatically after bench migrate."""
    print("[Koinonia Assistant] Running post-migration verification...")
    setup_roles()
    setup_workspaces()
    setup_docperms()
    setup_vectordb()
    print("[Koinonia Assistant] Migration sync complete.")

def setup_roles():
    """Ensures all 13 hierarchical Catholic diocesan & parish roles exist in the database."""
    for r in ALL_CHURCH_ROLES:
        if not frappe.db.exists("Role", r):
            role_doc = frappe.new_doc("Role")
            role_doc.role_name = r
            role_doc.desk_access = 1
            role_doc.is_custom = 1
            role_doc.save(ignore_permissions=True)
            print(f"[Koinonia Assistant] Created Role: {r}")
    frappe.db.commit()

def setup_workspaces():
    """Ensures all Church workspaces exist with public access and all roles assigned."""
    ws_configs = [
        {"name": "Koinonia Assistant", "title": "Koinonia Assistant", "type": "Link", "link_type": "Page", "link_to": "koinonia-chat", "icon": "message-square"},
        {"name": "Parish Directory", "title": "Parish Directory", "type": "Workspace", "icon": "folder"},
        {"name": "Sacred Sacraments", "title": "Sacred Sacraments", "type": "Workspace", "icon": "book-open"}
    ]
    
    for cfg in ws_configs:
        name = cfg["name"]
        if not frappe.db.exists("Workspace", name):
            ws = frappe.new_doc("Workspace")
            ws.title = cfg["title"]
            ws.label = cfg["title"]
            ws.public = 1
            ws.icon = cfg.get("icon", "folder")
            if cfg.get("type") == "Link":
                ws.type = "Link"
                ws.link_type = cfg.get("link_type", "Page")
                ws.link_to = cfg.get("link_to", "koinonia-chat")
            for r in ALL_CHURCH_ROLES:
                ws.append("roles", {"role": r})
            ws.save(ignore_permissions=True)
            print(f"[Koinonia Assistant] Created public Workspace: {name}")
        else:
            ws = frappe.get_doc("Workspace", name)
            ws.public = 1
            existing = [r.role for r in ws.roles]
            changed = False
            for r in ALL_CHURCH_ROLES:
                if r not in existing:
                    ws.append("roles", {"role": r})
                    changed = True
            if changed:
                ws.save(ignore_permissions=True)
                print(f"[Koinonia Assistant] Updated Workspace roles for: {name}")
    frappe.db.commit()

def setup_docperms():
    """Configures read/write/create/report permissions on all 11 DocTypes for all roles."""
    for dt in DOCTYPES:
        if not frappe.db.exists("DocType", dt):
            continue
            
        for role in ALL_CHURCH_ROLES:
            can_write = 1 if role in WRITE_ROLES else 0
            can_create = 1 if role in WRITE_ROLES else 0
            can_delete = 1 if role in ADMIN_ROLES else 0
            
            exists = frappe.db.sql("""
                SELECT name FROM `tabCustom DocPerm` 
                WHERE parent = %s AND role = %s
            """, (dt, role), as_dict=True)
            
            if not exists:
                cdp = frappe.new_doc("Custom DocPerm")
                cdp.parent = dt
                cdp.parenttype = "DocType"
                cdp.parentfield = "permissions"
                cdp.role = role
                cdp.read = 1
                cdp.write = can_write
                cdp.create = can_create
                cdp.delete = can_delete
                cdp.report = 1
                cdp.export = 1
                cdp.save(ignore_permissions=True)
            else:
                frappe.db.sql("""
                    UPDATE `tabCustom DocPerm` 
                    SET `read` = 1, `write` = %s, `create` = %s, `delete` = %s, `report` = 1, `export` = 1
                    WHERE parent = %s AND role = %s
                """, (can_write, can_create, can_delete, dt, role))
                
    frappe.db.commit()
    print("[Koinonia Assistant] Configured all Custom DocPerms across DocTypes and Roles.")

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
        print(f"[Koinonia Assistant] Vector DB auto-setup notice: {e}")
