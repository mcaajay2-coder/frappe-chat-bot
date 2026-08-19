import frappe
import frappe.sessions
from koinonia_assistant.api import resolve_user_jurisdiction

def get_context(context):
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.local.flags.redirect_location = "/login"
        raise frappe.Redirect
    
    jurisdiction = resolve_user_jurisdiction(user)
    fullname = jurisdiction.get("user_name") or user
    first_name = (fullname or "").split(" ")[0] if fullname else "U"
    
    context.user_email = user
    context.user_fullname = fullname
    context.user_first_name = first_name
    context.user_role = jurisdiction.get("user_role") or "Parish Priest"
    context.user_diocese = jurisdiction.get("user_diocese") or "Trichy"
    context.user_parish = jurisdiction.get("user_parish") or ""
    context.badge_text = jurisdiction.get("badge_text") or "Trichy Diocese"
    
    csrf = ""
    try:
        csrf = frappe.sessions.get_csrf_token()
    except Exception:
        pass
    if not csrf:
        try:
            csrf = getattr(frappe.local, "session", {}).get("data", {}).get("csrf_token", "")
        except Exception:
            pass
    context.csrf_token = csrf or ""
    return context
