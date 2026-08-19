import frappe
import requests
import json
import os
import psycopg2
import re

@frappe.whitelist()
def has_app_permission(user=None):
    """Frappe desktop permission hook function."""
    return True


PG_CONFIG = {
    "host":     os.getenv("PG_HOST",     "postgres-vector"),
    "port":     int(os.getenv("PG_PORT", 5432)),
    "dbname":   os.getenv("PG_DB",      "parish_vectordb"),
    "user":     os.getenv("PG_USER",    "postgres"),
    "password": os.getenv("PG_PASS",    "password"),
}

def clean_and_correct_voice_transcript(text: str) -> str:
    if not text or not str(text).strip():
        return ""
        
    cleaned = str(text).strip()
    
    # 1. Specialized Catholic Diocesan phonetic pattern replacements for Tamil / Tanglish Voice
    phonetic_fixes = [
        (r'\bcarrots?\b', 'vicars'),
        (r'\bkarots?\b', 'vicars'),
        (r'\bparis-?கள்\b', 'parishes'),
        (r'\bparis\b', 'parish'),
        (r'\bpariss\b', 'parish'),
        (r'\bpaaris\b', 'parish'),
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
        (r'\bmandalam\b', 'Zone'),
        (r'\bpeoples?\b', 'members'),
        (r'\bmembers-?gal\b', 'members'),
    ]
    for pat, rep in phonetic_fixes:
        cleaned = re.sub(pat, rep, cleaned, flags=re.IGNORECASE)
        
    # 2. Intelligent spelling & church terminology correction
    try:
        corr_res = correct_spelling(cleaned)
        if isinstance(corr_res, dict) and corr_res.get("corrected"):
            cleaned = corr_res["corrected"]
    except Exception as ce:
        print(f"[Voice Processor] Auto-correction notice: {ce}")
        
    return cleaned

@frappe.whitelist()
def transcribe_audio():
    """Transcribes uploaded audio using SarvamAI saaras:v3 model with full church voice processing."""
    if "audio" in frappe.request.files:
        audio_file = frappe.request.files["audio"]
        if audio_file and audio_file.filename:
            print("[Koinonia STT] Transcribing voice input...")
            sarvam_key = frappe.conf.get("sarvam_api_key")
            if not sarvam_key:
                return {"error": "SarvamAI API Key is missing from site configuration."}
            
            url = "https://api.sarvam.ai/speech-to-text"
            headers = {"api-subscription-key": sarvam_key}
            files = {"file": (audio_file.filename, audio_file.stream, audio_file.mimetype)}
            data = {"model": "saaras:v3", "mode": "codemix"}
            
            try:
                response = requests.post(url, headers=headers, files=files, data=data)
                response.raise_for_status()
                res_json = response.json()
                raw_transcript = res_json.get("transcript") or ""
                print(f"[Koinonia STT] Raw Transcript from STT: '{raw_transcript}'")
                
                # Strict church voice text processing & spell correction
                cleaned_transcript = clean_and_correct_voice_transcript(raw_transcript)
                print(f"[Koinonia STT] Processed & Corrected Transcript: '{cleaned_transcript}'")
                
                return {"transcript": cleaned_transcript, "raw_transcript": raw_transcript}
            except Exception as e:
                print(f"[Koinonia STT] Error: {e}")
                return {"error": f"Failed to transcribe audio: {str(e)}"}
    return {"error": "No audio file provided."}

global_roles = ["Bishop", "Diocesan Chancellor", "Vicar General", "Archbishop", "System Manager", "Administrator"]

def resolve_user_jurisdiction(user_email):
    if not user_email or user_email == "Guest":
        return {"user_role": "Guest", "user_diocese": "Trichy", "user_parish": None, "user_vicariate": None, "user_member_id": None, "user_parishes": [], "badge_text": "Guest", "user_name": "Guest"}

    user_roles = frappe.get_roles(user_email)
    user_fullname = frappe.db.get_value("User", user_email, "full_name") or frappe.db.get_value("User", user_email, "first_name") or user_email

    user_role = "Parishioner"
    user_parish = None
    user_vicariate = None
    user_member_id = None
    user_diocese = "Trichy"
    user_parishes = []
    
    # Check all available dioceses, vicariates, and parishes in database
    all_dioceses = frappe.db.sql_list("SELECT name FROM tabDiocese") if frappe.db.table_exists("Diocese") else ["Trichy", "Chennai", "Vellore", "Salem", "Coimbatore"]
    all_parishes = frappe.db.sql("SELECT name, vicariate_id, diocese_id FROM tabParish", as_dict=True) if frappe.db.table_exists("Parish") else []
    all_vicariates = frappe.db.sql("SELECT DISTINCT vicariate_id AS name, diocese_id FROM tabParish WHERE vicariate_id IS NOT NULL", as_dict=True) if frappe.db.table_exists("Parish") else []

    # 0. Administrator / System Manager (Global Superuser)
    if "Administrator" in user_roles or "System Manager" in user_roles or user_email in ["Administrator", "ajaijosem112@gmail.com"]:
        user_role = "Administrator"
        user_diocese = "All Dioceses"
        user_parish = None
        user_vicariate = None
        user_member_id = None
        user_parishes = [p['name'] for p in all_parishes]
        badge_text = "👑 Administrator (Global Access - All Dioceses & Parishes)"
        return {
            "user_email": user_email,
            "user_name": user_fullname,
            "user_role": user_role,
            "user_diocese": user_diocese,
            "user_parish": user_parish,
            "user_vicariate": user_vicariate,
            "user_parishes": user_parishes,
            "user_member_id": user_member_id,
            "badge_text": badge_text
        }

    # 1. Vicar General / Vicar Forane
    if "Vicar General" in user_roles or "Vicar Forane" in user_roles or "vicar general" in user_fullname.lower() or "vicar forane" in user_fullname.lower() or "vg_" in user_email.lower() or "vf_" in user_email.lower():
        user_role = "Vicar General" if ("Vicar General" in user_roles or "vicar general" in user_fullname.lower() or "vg_" in user_email.lower()) else "Vicar Forane"
        
        # Match vicariate from user full_name or email
        best_v = None
        for v in all_vicariates:
            v_name = v['name']
            v_clean = v_name.replace(" - ", " ").replace("-", " ").lower()
            u_clean = (user_fullname + " " + user_email).replace("___", " ").replace("__", " ").replace("_", " ").replace("-", " ").lower()
            
            v_words = [w for w in v_clean.split() if w not in ["vicariate", "the"]]
            if all(w in u_clean for w in v_words):
                best_v = v
                break
            elif any(w in u_clean.split() for w in v_words if w in ["east", "west", "north", "south", "central", "upper"]):
                if not best_v:
                    best_v = v
                    
        if best_v:
            user_vicariate = best_v['name']
            user_diocese = best_v['diocese_id']
                
        if not user_vicariate and all_vicariates:
            # Fallback match by diocese in name
            for d in all_dioceses:
                if d.lower() in user_fullname.lower() or d.lower() in user_email.lower():
                    user_diocese = d
                    for v in all_vicariates:
                        if v['diocese_id'] == d:
                            user_vicariate = v['name']
                            break
                    break
                    
        if user_vicariate:
            user_parishes = [p['name'] for p in all_parishes if p.get('vicariate_id') == user_vicariate]
            v_short = user_vicariate.split(" - ")[0] if " - " in user_vicariate else user_vicariate
            if user_parishes:
                parish_names_short = ", ".join([p.replace(" Parish", "").replace(" Church", "").replace(" Cathedral", "").strip() for p in user_parishes])
                badge_text = f"{v_short} [{parish_names_short}] ({user_diocese} Diocese)"
            else:
                badge_text = f"{v_short} ({user_diocese} Diocese)"
        else:
            badge_text = f"{user_role} ({user_diocese} Diocese)"

    # 2. Bishop (Ordinary of the Diocese)
    elif "Bishop" in user_roles or ("bishop" in user_fullname.lower() and "secretary" not in user_fullname.lower()) or "bishop_" in user_email.lower() or user_email == "bishop@example.com":
        user_role = "Bishop"
        for d in all_dioceses:
            d_clean = d.replace(" Diocese", "").strip()
            if d_clean and (d_clean.lower() in user_fullname.lower() or d_clean.lower() in user_email.lower()):
                user_diocese = d_clean
                break
        badge_text = f"{user_diocese} Diocese"

    # 3. Parish Priest
    elif "Parish Priest" in user_roles or "parish priest" in user_fullname.lower() or "priest" in user_email.lower():
        user_role = "Parish Priest"
        member_parish = frappe.db.get_value("Member", {"email": user_email}, "parish_id")
        if not member_parish:
            for p in all_parishes:
                short_p = p['name'].replace("Parish", "").replace("Church", "").replace("Cathedral", "").strip()
                if short_p and (short_p.lower() in user_fullname.lower() or short_p.lower() in user_email.lower()):
                    member_parish = p['name']
                    break
        user_parish = member_parish or "Christ the King Parish"
        diocese_name = frappe.db.get_value("Parish", user_parish, "diocese_id") or "Trichy"
        user_diocese = diocese_name.replace(" Diocese", "").strip()
        badge_text = f"{user_parish} ({user_diocese} Diocese)"

    # 4. Diocesan Curia & Staff
    elif any(r in user_roles for r in ["Chancellor", "Curia", "Financial Administrator", "Secretary to the Bishop", "Commission Director", "Institution Head", "Staff"]):
        for r in ["Chancellor", "Curia", "Financial Administrator", "Secretary to the Bishop", "Commission Director", "Institution Head", "Staff"]:
            if r in user_roles:
                user_role = r
                break
        for d in all_dioceses:
            if d.lower() in user_fullname.lower() or d.lower() in user_email.lower():
                user_diocese = d
                break
        badge_text = f"{user_role} ({user_diocese} Diocese)"

    # 5. Parishioner
    else:
        user_role = "Parishioner"
        member_doc = frappe.db.get_value("Member", {"email": user_email}, ["name", "parish_id"], as_dict=True)
        if member_doc:
            user_member_id = member_doc.get("name")
            user_parish = member_doc.get("parish_id")
        
        if user_parish:
            diocese_name = frappe.db.get_value("Parish", user_parish, "diocese_id") or "Trichy"
            user_diocese = diocese_name.replace(" Diocese", "").strip()
            badge_text = f"{user_parish} ({user_diocese} Diocese)"
        else:
            badge_text = f"{user_diocese} Diocese"

    return {
        "user_email": user_email,
        "user_name": user_fullname,
        "user_role": user_role,
        "user_diocese": user_diocese,
        "user_parish": user_parish,
        "user_vicariate": user_vicariate,
        "user_parishes": user_parishes,
        "user_member_id": user_member_id,
        "badge_text": badge_text
    }

@frappe.whitelist(allow_guest=False)
def get_user_session_info():
    return resolve_user_jurisdiction(frappe.session.user)

@frappe.whitelist(allow_guest=False)
def process_message(query_text=None, history=None, reference_text=None):
    """Processes sacrament and parish questions using the LangGraph RAG pipeline."""
    if query_text is None:
        query_text = frappe.form_dict.get("query_text")
    if history is None:
        history = frappe.form_dict.get("history")
    if reference_text is None:
        reference_text = frappe.form_dict.get("reference_text")
    
    # 1. Handle Audio input if uploaded via multipart/form-data
    has_audio = False
    try:
        if hasattr(frappe, "request") and frappe.request and hasattr(frappe.request, "files"):
            has_audio = "audio" in frappe.request.files
    except Exception:
        pass

    if has_audio:
        audio_file = frappe.request.files["audio"]
        if audio_file and audio_file.filename:
            print("[Koinonia Chat] Received audio upload. Transcribing...")
            sarvam_key = frappe.conf.get("sarvam_api_key")
            if not sarvam_key:
                return {"error": "SarvamAI API Key is missing from site configuration."}
            
            url = "https://api.sarvam.ai/speech-to-text"
            headers = {"api-subscription-key": sarvam_key}
            files = {"file": (audio_file.filename, audio_file.stream, audio_file.mimetype)}
            data = {"model": "saaras:v3", "mode": "codemix"}
            
            try:
                response = requests.post(url, headers=headers, files=files, data=data)
                response.raise_for_status()
                res_json = response.json()
                raw_transcript = res_json.get("transcript") or ""
                print(f"[Koinonia Chat] Raw Audio transcript: '{raw_transcript}'")
                
                query_text = clean_and_correct_voice_transcript(raw_transcript)
                print(f"[Koinonia Chat] Audio processed & corrected to: '{query_text}'")
            except Exception as e:
                print(f"[Koinonia Chat] Audio transcription error: {e}")
                return {"error": f"Failed to transcribe audio: {str(e)}"}

    if not query_text:
        return {"error": "No text or audio query provided."}

    query_text = clean_and_correct_voice_transcript(query_text)

    # Parse history if provided
    parsed_history = []
    if history:
        if isinstance(history, list):
            parsed_history = history
        elif isinstance(history, str):
            try:
                parsed_history = json.loads(history)
            except Exception as he:
                print(f"[Koinonia Chat] Warning: Failed to parse history: {he}")

    # 2. Resolve Role-Based Jurisdiction Boundaries
    user_email = frappe.session.user
    if user_email == "Guest":
        return {"error": "Authentication required. Please log in to use the assistant."}

    jurisdiction = resolve_user_jurisdiction(user_email)
    user_role = jurisdiction["user_role"]
    user_diocese = jurisdiction["user_diocese"]
    user_parish = jurisdiction["user_parish"]
    user_vicariate = jurisdiction["user_vicariate"]
    user_member_id = jurisdiction["user_member_id"]

    print(f"[Koinonia Chat] User: {user_email} | Role: {user_role} | Diocese: {user_diocese} | Parish: {user_parish} | Vicariate: {user_vicariate} | Ref: {reference_text}")

    # 3. Invoke LangGraph RAG pipeline
    try:
        from koinonia_assistant.rag.rag_engine import run_query
        result = run_query(
            query_text, 
            history=parsed_history, 
            reference_text=reference_text,
            user_role=user_role, 
            user_diocese=user_diocese,
            user_parish=user_parish,
            user_vicariate=user_vicariate,
            user_parishes=jurisdiction.get("user_parishes") or [],
            user_member_id=user_member_id,
            user_email=user_email
        )
        
        # Get query ID for feedback via Postgres
        conn = psycopg2.connect(**PG_CONFIG)
        query_id = -1
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM koinonia_query_history WHERE user_question = %s ORDER BY id DESC LIMIT 1;",
                    (query_text,)
                )
                row = cur.fetchone()
                if row:
                    query_id = row[0]
        finally:
            conn.close()

        reply = result.get("reply", "")
        generated_sql = result.get("generated_sql", "")
        is_direct = reply.startswith("👋") or reply.startswith("🤔")
        sql_rows = result.get("sql_result") or []
        
        if isinstance(sql_rows, list):
            for r in sql_rows:
                if isinstance(r, dict) and "full_name" not in r:
                    parts = [
                        r.get("first_name") or r.get("bridegroom_name") or r.get("bride_name"),
                        r.get("middle_name") or r.get("bridegroom_middle_name") or r.get("bride_middle_name"),
                        r.get("last_name") or r.get("bridegroom_last_name") or r.get("bride_last_name")
                    ]
                    fn_str = " ".join([str(p).strip() for p in parts if p and str(p).strip() not in ("", "None", "null", "NULL")]).strip()
                    if fn_str:
                        r["full_name"] = fn_str
        
        suggested_qs = result.get("suggested_questions") or []
        return {
            "user_message": query_text,
            "reply": reply,
            "generated_sql": "" if is_direct else generated_sql,
            "data": sql_rows,
            "query_id": query_id,
            "suggested_questions": suggested_qs
        }

    except Exception as e:
        print(f"[Koinonia Chat] Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "user_message": query_text,
            "reply": "🙏 I couldn't complete this query right now. Please try asking again or rephrasing your question in a moment! 😊",
            "generated_sql": "",
            "data": [],
            "query_id": -1
        }

@frappe.whitelist()
def log_query_feedback(query_id=None, is_correct=None):
    """Updates correctness flag for human feedback in koinonia_query_history."""
    if query_id is None or is_correct is None:
        frappe.throw("query_id and is_correct are required.")

    try:
        query_id = int(query_id)
        flag = 1 if str(is_correct).lower() == "true" else 0

        conn = psycopg2.connect(**PG_CONFIG)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE koinonia_query_history SET correctness_flag = %s WHERE id = %s;",
                (flag, query_id)
            )
        conn.commit()
        conn.close()

        print(f"[Koinonia Feedback] Query {query_id} marked as {flag}")
        return {"success": True, "query_id": query_id, "correctness_flag": flag}

    except Exception as e:
        print(f"[Koinonia Feedback] Error: {e}")
        return {"success": False, "error": str(e)}

# ─── pgvector Hook Triggers ───────────────────────────────────────────────────

def sync_doctype_schema(doc, method=None):
    """Real-time sync of table schemas and fields to pgvector, restricted to custom sacrament DocTypes."""
    custom_doctypes = {
        "Family", "Member", "Baptism", "Communion", "Confirmation", "Marriage", 
        "Anointing Of Sick", "Death", "Diocese", "Vicariate", "Parish"
    }
    if doc.name not in custom_doctypes:
        return

    try:
        table_name = f"tab{doc.name}"
        print(f"[Koinonia Hook] Syncing schema for {doc.name} (table: {table_name}) to pgvector...")
        
        columns = frappe.db.sql("""
            SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_KEY
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION;
        """, (frappe.conf.db_name, table_name), as_dict=True)
        
        if not columns:
            return

        lines = [
            f"Table Name: `{table_name}`",
            f"Entity/Concept: {doc.name}",
            "Columns:"
        ]
        for col in columns:
            nullable_str = "nullable" if col["IS_NULLABLE"] == "YES" else "NOT NULL"
            key_str      = f" [{col['COLUMN_KEY']}]" if col["COLUMN_KEY"] else ""
            lines.append(f"  - `{col['COLUMN_NAME']}` ({col['COLUMN_TYPE']}, {nullable_str}){key_str}")
        description = "\n".join(lines)

        from koinonia_assistant.rag.ingest import embed_text, build_field_description, upsert_pg_field
        embedding = embed_text(description)

        conn = psycopg2.connect(**PG_CONFIG)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO koinonia_table_schemas (table_name, schema_ddl, embedding)
                VALUES (%s, %s, %s::vector)
                ON CONFLICT (table_name) DO UPDATE
                    SET schema_ddl = EXCLUDED.schema_ddl,
                        embedding  = EXCLUDED.embedding;
            """, (table_name, description, embedding))
        conn.commit()
        conn.close()
        print(f"[Koinonia Hook] Successfully synced table schema for {table_name} to pgvector.")

        # Sync field-level schemas in real-time
        print(f"[Koinonia Hook] Syncing fields for {table_name} to pgvector...")
        for col in columns:
            col_name = col["COLUMN_NAME"]
            col_type = col["COLUMN_TYPE"]
            
            # Skip standard meta fields
            if col_name in ["name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "_user_tags", "_comments", "_assign", "_liked_by"]:
                continue
                
            label, desc = build_field_description(table_name, col_name, col_type)
            emb = embed_text(desc)
            upsert_pg_field(table_name, col_name, col_type, label, desc, emb)
        print(f"[Koinonia Hook] Successfully synced all fields for {table_name} to pgvector.")

    except Exception as e:
        print(f"[Koinonia Hook] Error syncing schema: {e}")

def delete_doctype_schema(doc, method=None):
    """Deletes custom table and field schemas from pgvector when custom DocType is deleted."""
    custom_doctypes = {
        "Family", "Member", "Baptism", "Communion", "Confirmation", "Marriage", 
        "Anointing Of Sick", "Death", "Diocese", "Vicariate", "Parish"
    }
    if doc.name not in custom_doctypes:
        return

    try:
        table_name = f"tab{doc.name}"
        print(f"[Koinonia Hook] Deleting schema/fields for {doc.name} (table: {table_name}) from pgvector...")
        
        conn = psycopg2.connect(**PG_CONFIG)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM koinonia_table_schemas WHERE table_name = %s;", (table_name,))
            cur.execute("DELETE FROM koinonia_field_schemas WHERE table_name = %s;", (table_name,))
        conn.commit()
        conn.close()
        print(f"[Koinonia Hook] Successfully deleted schema/fields for {table_name} from pgvector.")

    except Exception as e:
        print(f"[Koinonia Hook] Error deleting schema: {e}")

@frappe.whitelist()
def create_test_users():
    """Populates test roles and users for testing RBAC."""
    print("Checking and creating Roles...")
    roles = [
        "Bishop", "Curia", "Vicar General", "Chancellor", 
        "Financial Administrator", "Secretary to the Bishop", 
        "Vicar Forane", "Parish Priest", "Commission Director", 
        "Institution Head", "Staff", "Priest", "Parishioner"
    ]
    
    for r in roles:
        if not frappe.db.exists("Role", r):
            role_doc = frappe.get_doc({"doctype": "Role", "role_name": r})
            role_doc.insert(ignore_permissions=True)
            print(f" - Created Role: {r}")
    frappe.db.commit()

    test_users = [
        {"email": "bishop@example.com", "first_name": "Test Bishop", "role": "Bishop"},
        {"email": "curia@example.com", "first_name": "Test Curia", "role": "Curia"},
        {"email": "vicargeneral@example.com", "first_name": "Test Vicar General", "role": "Vicar General"},
        {"email": "chancellor@example.com", "first_name": "Test Chancellor", "role": "Chancellor"},
        {"email": "financialadmin@example.com", "first_name": "Test Financial Admin", "role": "Financial Administrator"},
        {"email": "secretary@example.com", "first_name": "Test Secretary", "role": "Secretary to the Bishop"},
        {"email": "vicarforane@example.com", "first_name": "Test Vicar Forane", "role": "Vicar Forane"},
        {"email": "parishpriest@example.com", "first_name": "Test Parish Priest", "role": "Parish Priest"},
        {"email": "commissiondirector@example.com", "first_name": "Test Commission Director", "role": "Commission Director"},
        {"email": "institutionhead@example.com", "first_name": "Test Institution Head", "role": "Institution Head"},
        {"email": "staff@example.com", "first_name": "Test Staff", "role": "Staff"},
        {"email": "priest@example.com", "first_name": "Test Priest", "role": "Priest"},
        {"email": "parishioner@example.com", "first_name": "Test Parishioner", "role": "Parishioner"}
    ]

    print("\nChecking and creating Test Users...")
    for u in test_users:
        email = u["email"]
        if not frappe.db.exists("User", email):
            user = frappe.get_doc({
                "doctype": "User",
                "email": email,
                "first_name": u["first_name"],
                "send_welcome_email": 0
            })
            user.insert(ignore_permissions=True)
            
            # Use frappe's internal utility to set password properly
            from frappe.utils.password import update_password
            update_password(email, "Password123@")
            
            user.add_roles(u["role"])
            print(f" - Created user: {email} (Role: {u['role']})")
        else:
            user = frappe.get_doc("User", email)
            if u["role"] not in frappe.get_roles(email):
                user.add_roles(u["role"])
            
            from frappe.utils.password import update_password
            update_password(email, "Password123@")
            print(f" - Updated user: {email} (Role: {u['role']})")
            
    frappe.db.commit()
    return "All test users have been created with password: Password123@"

@frappe.whitelist()
def fix_page_roles():
    page = frappe.get_doc("Page", "koinonia-chat")
    page.standard = "Yes"
    existing_roles = [r.role for r in page.roles]
    needed_roles = ["System Manager", "Administrator", "Bishop", "Curia", "Vicar General", "Chancellor", "Financial Administrator", "Secretary to the Bishop", "Vicar Forane", "Parish Priest", "Commission Director", "Institution Head", "Staff", "Priest", "Parishioner"]
    for r in needed_roles:
        if r not in existing_roles:
            page.append("roles", {"role": r})
    page.save(ignore_permissions=True)
    frappe.db.commit()
    print("Page permissions completely fixed in DB!")

@frappe.whitelist()
def fix_workspace():
    if frappe.db.exists("Workspace", "parish_chat"):
        ws = frappe.get_doc("Workspace", "parish_chat")
        ws.type = "Link"
        ws.link_type = "Page"
        ws.link_to = "koinonia-chat"
        ws.save(ignore_permissions=True)
        frappe.db.commit()
        print("Workspace 'parish_chat' updated to point to 'koinonia-chat'!")
    else:
        print("Workspace not found")

@frappe.whitelist()
def create_public_workspace():
    if not frappe.db.exists("Workspace", "Koinonia Assistant"):
        ws = frappe.new_doc("Workspace")
        ws.title = "Koinonia Assistant"
        ws.label = "Koinonia Assistant"
        ws.type = "Link"
        ws.link_type = "Page"
        ws.link_to = "koinonia-chat"
        ws.public = 1
        ws.icon = "message-square"
        ws.save(ignore_permissions=True)
        frappe.db.commit()
        print("Public Workspace 'Koinonia Assistant' created!")
    else:
        print("Public Workspace already exists.")

@frappe.whitelist()
def fix_workspace_roles():
    ws = frappe.get_doc("Workspace", "Koinonia Assistant")
    existing_roles = [r.role for r in ws.roles]
    needed_roles = ["System Manager", "Administrator", "Bishop", "Curia", "Vicar General", "Chancellor", "Financial Administrator", "Secretary to the Bishop", "Vicar Forane", "Parish Priest", "Commission Director", "Institution Head", "Staff", "Priest", "Parishioner"]
    for r in needed_roles:
        if r not in existing_roles:
            ws.append("roles", {"role": r})
    ws.save(ignore_permissions=True)
    frappe.db.commit()
    print("Workspace roles completely fixed in DB!")

@frappe.whitelist(allow_guest=False)
def correct_spelling(text=None, preserve_tamil=False):
    if not text:
        text = frappe.form_dict.get("text")
    if not text or not text.strip():
        return {"corrected": "", "corrected_text": ""}
    
    text_clean = text.strip()
    is_tamil = preserve_tamil or bool(re.search(r'[\u0B80-\u0BFF]', text_clean))
    
    try:
        from koinonia_assistant.rag.rag_engine import invoke_llm_with_rotation
        
        if is_tamil:
            sys_msg = (
                "You are an intelligent Catholic Church assistant that corrects speech recognition typos in Tamil / Tanglish questions.\n"
                "The user is asking a question in Tamil script. Understand church context and correct phonetic speech mistakes:\n"
                "- 'புதுப்பணி' / 'புதுபணி' -> 'புது நன்மை' (First Holy Communion)\n"
                "- 'கல்யாணம்' -> 'திருமணம்' (Holy Matrimony / Marriage)\n"
                "- 'ஞானஸ்தானம்' -> 'ஞானஸ்நானம்' (Baptism)\n"
                "- 'carrots' -> 'vicars' / 'விகார்ஸ்'\n"
                "- 'பரிஷ்' / 'பாரிஸ்' -> 'பங்கு' (Parish)\n"
                "- 'family code' -> 'family card / குடும்ப அட்டை'\n"
                "CRITICAL LANGUAGE RULE: The user wants their question displayed in TAMIL. Keep the sentence in TAMIL script. DO NOT translate the Tamil question into English!\n"
                "Return ONLY the corrected Tamil question string. Do not add quotes, explanations, or markdown."
            )
        else:
            sys_msg = (
                "You are an intelligent spelling, grammar, and church terminology correction assistant for a Parish database assistant.\n"
                "Your job is to correct spelling errors, typos, phonetic Tanglish/English transliterations, and grammatical mistakes in the user's question.\n"
                "Examples:\n"
                "- 'shwo all merriage recrods' -> 'Show all marriage records'\n"
                "- 'list membes who completed baptizum' -> 'List members who completed baptism'\n"
                "- 'who is the family head in st joshep parish' -> 'Who is the family head in St. Joseph Parish'\n"
                "CRITICAL RULE: Return ONLY the corrected question string. Do not add quotes, markdown, explanations, or any extra text."
            )
        
        prompt = [
            ("system", sys_msg),
            ("human", text_clean)
        ]
        
        response = invoke_llm_with_rotation(prompt)
        corrected = response.content.strip().strip('"').strip("'")
        return {"corrected": corrected, "corrected_text": corrected}
    except Exception as e:
        print(f"[correct_spelling] Error: {e}")
        # Quick dictionary fallback
        corrections = {
            "babtism": "Baptism", "baptizm": "Baptism", "parsh": "Parish",
            "marige": "Marriage", "marrige": "Marriage", "famly": "Family",
            "famlies": "Families", "comunion": "Holy Communion", "dioce": "Diocese",
            "membr": "Member", "membrs": "Members", "st josef": "St. Joseph's"
        }
        words = text_clean.split()
        fallback_words = [corrections.get(w.lower(), w) for w in words]
        corrected_fallback = " ".join(fallback_words)
        return {"corrected": corrected_fallback, "corrected_text": corrected_fallback}

@frappe.whitelist(allow_guest=False)
def fix_spelling(text=None):
    return correct_spelling(text=text)

# ─── Desk Role-Based Jurisdictional Permission Queries ─────────────────────────

def get_diocese_permission_query_conditions(user=None):
    if not user:
        user = frappe.session.user
    if user in ["Administrator", "ajaijosem112@gmail.com"] or "System Manager" in frappe.get_roles(user):
        return ""
    j = resolve_user_jurisdiction(user)
    role = j.get("user_role")
    diocese = j.get("user_diocese")
    if role in ["Bishop", "Chancellor", "Curia"] and diocese and diocese != "All Dioceses":
        return f"(`tabDiocese`.`name` = {frappe.db.escape(diocese)} OR `tabDiocese`.`diocese_name` = {frappe.db.escape(diocese)})"
    return ""

def get_vicariate_permission_query_conditions(user=None):
    if not user:
        user = frappe.session.user
    if user in ["Administrator", "ajaijosem112@gmail.com"] or "System Manager" in frappe.get_roles(user):
        return ""
    j = resolve_user_jurisdiction(user)
    role = j.get("user_role")
    diocese = j.get("user_diocese")
    vicariate = j.get("user_vicariate")
    if role in ["Bishop", "Chancellor", "Curia"] and diocese and diocese != "All Dioceses":
        return f"(`tabVicariate`.`diocese_id` = {frappe.db.escape(diocese)})"
    elif role in ["Vicar General", "Vicar Forane"] and vicariate:
        return f"(`tabVicariate`.`name` = {frappe.db.escape(vicariate)} OR `tabVicariate`.`vicariate_name` = {frappe.db.escape(vicariate)})"
    return ""

def get_parish_permission_query_conditions(user=None):
    if not user:
        user = frappe.session.user
    if user in ["Administrator", "ajaijosem112@gmail.com"] or "System Manager" in frappe.get_roles(user):
        return ""
    j = resolve_user_jurisdiction(user)
    role = j.get("user_role")
    diocese = j.get("user_diocese")
    parish = j.get("user_parish")
    parishes = j.get("user_parishes") or []
    
    if role in ["Bishop", "Chancellor", "Curia"] and diocese and diocese != "All Dioceses":
        return f"(`tabParish`.`diocese_id` = {frappe.db.escape(diocese)})"
    elif role in ["Vicar General", "Vicar Forane"] and parishes:
        p_list = ", ".join([frappe.db.escape(p) for p in parishes])
        return f"(`tabParish`.`name` IN ({p_list}) OR `tabParish`.`parish_name` IN ({p_list}))"
    elif role == "Parish Priest" and parish:
        return f"(`tabParish`.`name` = {frappe.db.escape(parish)} OR `tabParish`.`parish_name` = {frappe.db.escape(parish)})"
    elif role in ["Parishioner", "Member"] and parish:
        return f"(`tabParish`.`name` = {frappe.db.escape(parish)})"
    return ""

def get_generic_church_permission_conditions(doctype_table, user=None):
    if not user:
        user = frappe.session.user
    if user in ["Administrator", "ajaijosem112@gmail.com"] or "System Manager" in frappe.get_roles(user):
        return ""
    j = resolve_user_jurisdiction(user)
    role = j.get("user_role")
    diocese = j.get("user_diocese")
    parish = j.get("user_parish")
    parishes = j.get("user_parishes") or []
    
    if role in ["Bishop", "Chancellor", "Curia"] and diocese and diocese != "All Dioceses":
        return f"(`{doctype_table}`.`diocese_id` = {frappe.db.escape(diocese)})"
    elif role in ["Vicar General", "Vicar Forane"] and parishes:
        p_list = ", ".join([frappe.db.escape(p) for p in parishes])
        return f"(`{doctype_table}`.`parish_id` IN ({p_list}))"
    elif role == "Parish Priest" and parish:
        return f"(`{doctype_table}`.`parish_id` = {frappe.db.escape(parish)})"
    return ""

def get_family_permission_query_conditions(user=None):
    return get_generic_church_permission_conditions("tabFamily", user)

def get_member_permission_query_conditions(user=None):
    return get_generic_church_permission_conditions("tabMember", user)

def get_baptism_permission_query_conditions(user=None):
    return get_generic_church_permission_conditions("tabBaptism", user)

def get_communion_permission_query_conditions(user=None):
    return get_generic_church_permission_conditions("tabCommunion", user)

def get_confirmation_permission_query_conditions(user=None):
    return get_generic_church_permission_conditions("tabConfirmation", user)

def get_marriage_permission_query_conditions(user=None):
    return get_generic_church_permission_conditions("tabMarriage", user)

def get_death_permission_query_conditions(user=None):
    return get_generic_church_permission_conditions("tabDeath", user)


