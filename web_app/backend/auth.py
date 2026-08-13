import os
from typing import Dict, Any
from fastapi import Request

def extract_user_from_request(request: Request) -> Dict[str, Any]:
    """
    Extracts authenticated user identity from GCP Identity-Aware Proxy (IAP) headers.
    Header injected by IAP: x-goog-authenticated-user-email: accounts.google.com:user@company.com
    Falls back to local dev header x-dev-user-email or default dev identity.
    """
    # 1. Check IAP Google Workspace authenticated header
    iap_email_header = request.headers.get("x-goog-authenticated-user-email", "")
    if iap_email_header:
        # Strip "accounts.google.com:" prefix
        email = iap_email_header.replace("accounts.google.com:", "").strip().lower()
        if email:
            return {
                "user_id": email,
                "email": email,
                "display_name": get_user_display_name(email),
                "auth_type": "gcp_iap"
            }

    # 2. Check local dev switcher header (e.g. from SessionSidebar)
    dev_email_header = request.headers.get("x-dev-user-email", "")
    if dev_email_header and dev_email_header.strip():
        email = dev_email_header.strip().lower()
        return {
            "user_id": email,
            "email": email,
            "display_name": get_user_display_name(email),
            "auth_type": "dev_local"
        }

    # 3. Default local developer fallback identity
    default_email = os.getenv("DEFAULT_USER_EMAIL", "auditor.john@company.com")
    return {
        "user_id": default_email,
        "email": default_email,
        "display_name": get_user_display_name(default_email),
        "auth_type": "dev_default"
    }

def get_user_display_name(email: str) -> str:
    """Formats an email string into a clean display name (e.g. auditor.john@company.com -> Auditor John)"""
    if not email or "@" not in email:
        return "Auditor"
    local_part = email.split("@")[0]
    words = local_part.replace(".", " ").replace("_", " ").split()
    return " ".join(w.capitalize() for w in words) if words else "Auditor"
