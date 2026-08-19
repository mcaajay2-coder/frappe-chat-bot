import frappe

def run():
    print("Starting Parish Cleanup...")
    # Find all parishes that are currently used in tabMember
    used_parishes = frappe.db.sql_list("SELECT DISTINCT parish_id FROM `tabMember` WHERE parish_id IS NOT NULL AND parish_id != ''")
    
    # Get all parishes
    all_parishes = frappe.db.sql_list("SELECT name FROM `tabParish`")
    
    unwanted = [p for p in all_parishes if p not in used_parishes]
    
    print(f"Keeping {len(used_parishes)} parishes: {used_parishes}")
    print(f"Found {len(unwanted)} unwanted parishes to delete...")
    
    deleted_count = 0
    for p in unwanted:
        try:
            frappe.delete_doc("Parish", p, ignore_permissions=True, force=True)
            deleted_count += 1
            print(f"Deleted Parish: {p}")
        except Exception as e:
            print(f"Failed to delete {p}: {e}")
            
    print(f"Successfully deleted {deleted_count} unwanted parishes.")
    frappe.db.commit()
