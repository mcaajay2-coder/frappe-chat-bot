import frappe
from frappe.utils.password import update_password
import random
from datetime import date, timedelta

DOCTYPES = [
    "Diocese", "Vicariate", "Parish", "Sub Station", "Family", "Member",
    "Baptism", "Communion", "Confirmation", "Marriage", "Anointing Of Sick", "Death"
]

ALL_CHURCH_ROLES = [
    "Bishop", "Curia", "Vicar General", "Chancellor", "Financial Administrator",
    "Secretary to the Bishop", "Vicar Forane", "Parish Priest", "Commission Director",
    "Institution Head", "Staff", "Priest", "Parishioner", "Desk User", "System Manager"
]

ADMIN_ROLES = ["Bishop", "Vicar General", "Chancellor", "System Manager", "Administrator"]
WRITE_ROLES = ["Bishop", "Vicar General", "Chancellor", "Parish Priest", "Staff", "System Manager", "Administrator"]

def after_install():
    """Executed automatically when koinonia_assistant is installed on any Frappe site."""
    print("[Koinonia Assistant] Running post-installation setup...")
    sync_all_doctypes_and_workspaces()
    setup_roles()
    setup_workspaces()
    setup_docperms()
    seed_sample_data()
    setup_vectordb()
    print("[Koinonia Assistant] Installation complete! All doctypes, data, permissions & icons are ready.")

def after_migrate():
    """Executed automatically after bench migrate."""
    print("[Koinonia Assistant] Running post-migration verification...")
    sync_all_doctypes_and_workspaces()
    setup_roles()
    setup_workspaces()
    setup_docperms()
    setup_vectordb()
    print("[Koinonia Assistant] Migration sync complete.")

def sync_all_doctypes_and_workspaces():
    """Forces immediate synchronization of all DocTypes and Workspaces from disk into MariaDB."""
    try:
        from frappe.model.sync import sync_for
        print("[Koinonia Assistant] Syncing DocTypes and Workspaces from files...")
        sync_for("koinonia_assistant", force=True, reset_permissions=True)
        frappe.db.commit()
    except Exception as e:
        print(f"[Koinonia Assistant] Notice during sync_for: {e}")

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
    """Configures read/write/create/report permissions on all DocTypes for all roles."""
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
    print("[Koinonia Assistant] Configured Custom DocPerms.")

def seed_sample_data(force=False):
    """Seeds starter Dioceses, Vicariates, Parishes, Members, Sacraments, and Demo Users."""
    if not force and frappe.db.exists("DocType", "Diocese"):
        count = frappe.db.count("Diocese")
        if count > 0:
            print(f"[Koinonia Assistant] Database already contains {count} Dioceses. Skipping auto-seed.")
            return

    print("[Koinonia Assistant] Seeding diocesan and sacramental sample data...")
    
    # 1. Dioceses
    dioceses = [
        {"name": "Trichy", "diocese_name": "Trichy", "diocese_code": "TRY", "bishop_name": "Most Rev. Bishop of Trichy", "city": "Tiruchirappalli", "active": 1},
        {"name": "Vellore", "diocese_name": "Vellore", "diocese_code": "VEL", "bishop_name": "Most Rev. Bishop of Vellore", "city": "Vellore", "active": 1}
    ]
    for d in dioceses:
        if not frappe.db.exists("Diocese", d["name"]):
            doc = frappe.get_doc({"doctype": "Diocese", **d})
            doc.insert(ignore_permissions=True)

    # 2. Vicariates
    vicariates = [
        {"name": "Central Vicariate - Trichy", "vicariate_name": "Central Vicariate - Trichy", "diocese_id": "Trichy", "vicar_forane": "Very Rev. Fr. Vicar Forane Central", "active": 1},
        {"name": "North Vicariate - Trichy", "vicariate_name": "North Vicariate - Trichy", "diocese_id": "Trichy", "vicar_forane": "Very Rev. Fr. Vicar Forane North", "active": 1},
        {"name": "Central Vicariate - Vellore", "vicariate_name": "Central Vicariate - Vellore", "diocese_id": "Vellore", "vicar_forane": "Very Rev. Fr. Vicar Forane Vellore Central", "active": 1},
        {"name": "North Vicariate - Vellore", "vicariate_name": "North Vicariate - Vellore", "diocese_id": "Vellore", "vicar_forane": "Very Rev. Fr. Vicar Forane Vellore North", "active": 1}
    ]
    for v in vicariates:
        if not frappe.db.exists("Vicariate", v["name"]):
            doc = frappe.get_doc({"doctype": "Vicariate", **v})
            doc.insert(ignore_permissions=True)

    # 3. Parishes
    parishes = [
        {"name": "Christ the King Parish", "parish_name": "Christ the King Parish", "diocese_id": "Trichy", "vicariate_id": "Central Vicariate - Trichy", "parish_priest": "Rev. Fr. Antony Xavier", "city": "Trichy", "active": 1},
        {"name": "Our Lady of Lourdes", "parish_name": "Our Lady of Lourdes", "diocese_id": "Trichy", "vicariate_id": "Central Vicariate - Trichy", "parish_priest": "Rev. Fr. Joseph Lourdes", "city": "Trichy", "active": 1},
        {"name": "St. Mary's Cathedral", "parish_name": "St. Mary's Cathedral", "diocese_id": "Trichy", "vicariate_id": "North Vicariate - Trichy", "parish_priest": "Rev. Fr. Cathedral Priest", "city": "Trichy", "active": 1},
        {"name": "Holy Cross Parish", "parish_name": "Holy Cross Parish", "diocese_id": "Trichy", "vicariate_id": "North Vicariate - Trichy", "parish_priest": "Rev. Fr. Francis Cross", "city": "Trichy", "active": 1},
        {"name": "Assumption Cathedral", "parish_name": "Assumption Cathedral", "diocese_id": "Vellore", "vicariate_id": "Central Vicariate - Vellore", "parish_priest": "Rev. Fr. Assumption Priest", "city": "Vellore", "active": 1},
        {"name": "St. Jude's Parish, Sathuvachari", "parish_name": "St. Jude's Parish, Sathuvachari", "diocese_id": "Vellore", "vicariate_id": "Central Vicariate - Vellore", "parish_priest": "Rev. Fr. Jude Priest", "city": "Vellore", "active": 1},
        {"name": "St. Antony's Parish", "parish_name": "St. Antony's Parish", "diocese_id": "Vellore", "vicariate_id": "North Vicariate - Vellore", "parish_priest": "Rev. Fr. Antony Priest", "city": "Vellore", "active": 1}
    ]
    for p in parishes:
        if not frappe.db.exists("Parish", p["name"]):
            doc = frappe.get_doc({"doctype": "Parish", **p})
            doc.insert(ignore_permissions=True)

    # 4. Users & Credentials
    seed_users = [
        {"email": "bishop_trichy@test.com", "first_name": "Bishop", "last_name": "Trichy", "role": "Bishop"},
        {"email": "bishop_vellore@test.com", "first_name": "Bishop", "last_name": "Vellore", "role": "Bishop"},
        {"email": "vg_trichy@test.com", "first_name": "Vicar General", "last_name": "Trichy", "role": "Vicar General"},
        {"email": "chancellor_trichy@test.com", "first_name": "Chancellor", "last_name": "Trichy", "role": "Chancellor"},
        {"email": "curia_trichy@test.com", "first_name": "Curia", "last_name": "Trichy", "role": "Curia"},
        {"email": "vf_trichy_central@test.com", "first_name": "Vicar Forane", "last_name": "Central", "role": "Vicar Forane"},
        {"email": "priest_christ_the_king_parish@test.com", "first_name": "Priest", "last_name": "Christ the King", "role": "Parish Priest"},
        {"email": "priest_our_lady_of_lourdes@test.com", "first_name": "Priest", "last_name": "Lourdes", "role": "Parish Priest"},
        {"email": "priest_st._marys_cathedral@test.com", "first_name": "Priest", "last_name": "St Marys", "role": "Parish Priest"},
        {"email": "priest_holy_cross_parish@test.com", "first_name": "Priest", "last_name": "Holy Cross", "role": "Parish Priest"},
        {"email": "parishioner_trichy@test.com", "first_name": "Parishioner", "last_name": "Trichy", "role": "Parishioner"}
    ]

    for u in seed_users:
        user_email = u["email"]
        if not frappe.db.exists("User", user_email):
            udoc = frappe.new_doc("User")
            udoc.email = user_email
            udoc.first_name = u["first_name"]
            udoc.last_name = u["last_name"]
            udoc.send_welcome_email = 0
            udoc.save(ignore_permissions=True)
            
            # Roles
            udoc.add_roles("Desk User", u["role"])
            update_password(user=user_email, pwd="password")
            print(f"[Koinonia Assistant] Created user: {user_email} (Role: {u['role']}, Password: password)")

    # 5. Members & Sacraments
    first_names = [
        "Joseph", "Mary", "Francis", "Anthony", "Theresa", "Ignatius", "Augustine", "Benedict",
        "Cecilia", "Dominic", "Catherine", "Xavier", "Sebastian", "Clara", "Bernard", "Rita",
        "Patrick", "Bridget", "Stephen", "Agnes", "Peter", "Paul", "Lucy", "Thomas", "Elizabeth",
        "Gabriel", "Veronica", "Michael", "Monica", "Andrew", "Martha", "Jude", "Genevieve"
    ]
    last_names = [
        "Fernandez", "D'Souza", "Gonzales", "Rodriguez", "Lourdusamy", "Arulraj", "Savarimuthu",
        "Marianathan", "Vasanth", "Susai", "Doss", "Xavier", "Amalraj", "Sebastian", "Paulraj"
    ]
    
    years = [2024, 2025, 2026]
    parish_keys = [
        ("Trichy", "Central Vicariate - Trichy", "Christ the King Parish"),
        ("Trichy", "Central Vicariate - Trichy", "Our Lady of Lourdes"),
        ("Trichy", "North Vicariate - Trichy", "St. Mary's Cathedral"),
        ("Trichy", "North Vicariate - Trichy", "Holy Cross Parish"),
        ("Vellore", "Central Vicariate - Vellore", "Assumption Cathedral"),
        ("Vellore", "Central Vicariate - Vellore", "St. Jude's Parish, Sathuvachari")
    ]

    for p_idx, (dio, vic, parish) in enumerate(parish_keys):
        # Create Families & Members
        for fam_i in range(1, 15):
            fcode = f"FC-{parish[:3].upper()}-{1000 + fam_i}"
            head_fn = random.choice(first_names)
            head_ln = random.choice(last_names)
            
            if frappe.db.exists("DocType", "Family"):
                fdoc = frappe.get_doc({
                    "doctype": "Family",
                    "family_code": fcode,
                    "head_of_family_name": f"{head_fn} {head_ln}",
                    "diocese_id": dio,
                    "vicariate_id": vic,
                    "parish_id": parish,
                    "active": 1
                })
                fdoc.insert(ignore_permissions=True)

            if frappe.db.exists("DocType", "Member"):
                mdoc = frappe.get_doc({
                    "doctype": "Member",
                    "first_name": head_fn,
                    "last_name": head_ln,
                    "family_card_no": fcode,
                    "diocese_id": dio,
                    "vicariate_id": vic,
                    "parish_id": parish,
                    "gender": "Male",
                    "living_status": "Alive",
                    "marital_status": "Married"
                })
                mdoc.insert(ignore_permissions=True)

            # Sacraments
            for yr in years:
                # Baptism
                if frappe.db.exists("DocType", "Baptism"):
                    bdoc = frappe.get_doc({
                        "doctype": "Baptism",
                        "first_name": random.choice(first_names),
                        "last_name": head_ln,
                        "bapt_date": f"{yr}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                        "bapt_parish_id": parish,
                        "diocese_id": dio,
                        "vicariate_id": vic,
                        "family_card_no": fcode,
                        "bapt_minister": f"Rev. Fr. {random.choice(first_names)}"
                    })
                    bdoc.insert(ignore_permissions=True)

                # Communion
                if frappe.db.exists("DocType", "Communion"):
                    cdoc = frappe.get_doc({
                        "doctype": "Communion",
                        "first_name": random.choice(first_names),
                        "last_name": head_ln,
                        "fhc_date": f"{yr}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                        "fhc_parish_id": parish,
                        "diocese_id": dio,
                        "vicariate_id": vic,
                        "family_card_no": fcode
                    })
                    cdoc.insert(ignore_permissions=True)

                # Confirmation
                if frappe.db.exists("DocType", "Confirmation"):
                    cnfdoc = frappe.get_doc({
                        "doctype": "Confirmation",
                        "first_name": random.choice(first_names),
                        "last_name": head_ln,
                        "cnf_date": f"{yr}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                        "cnf_parish_id": parish,
                        "diocese_id": dio,
                        "vicariate_id": vic,
                        "family_card_no": fcode,
                        "cnf_minister": f"Most Rev. Bishop of {dio}"
                    })
                    cnfdoc.insert(ignore_permissions=True)

                # Marriage
                if frappe.db.exists("DocType", "Marriage"):
                    mrgdoc = frappe.get_doc({
                        "doctype": "Marriage",
                        "bridegroom_name": f"{random.choice(first_names)} {head_ln}",
                        "bridegroom_last_name": head_ln,
                        "bride_name": f"{random.choice(first_names)} {random.choice(last_names)}",
                        "bride_last_name": random.choice(last_names),
                        "mrg_date": f"{yr}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                        "mrg_parish_id": parish,
                        "diocese_id": dio,
                        "vicariate_id": vic,
                        "family_card_no": fcode,
                        "mrg_minister": f"Rev. Fr. {random.choice(first_names)}"
                    })
                    mrgdoc.insert(ignore_permissions=True)

                # Death
                if frappe.db.exists("DocType", "Death"):
                    ddoc = frappe.get_doc({
                        "doctype": "Death",
                        "first_name": random.choice(first_names),
                        "last_name": head_ln,
                        "death_date": f"{yr}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                        "parish_id": parish,
                        "diocese_id": dio,
                        "vicariate_id": vic,
                        "family_card_no": fcode
                    })
                    ddoc.insert(ignore_permissions=True)

    frappe.db.commit()
    print("[Koinonia Assistant] Sample data seeded successfully across all Dioceses, Parishes & Sacraments.")

def setup_vectordb():
    """Initializes Postgres pgvector tables and runs schema ingestion if DB is accessible."""
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
