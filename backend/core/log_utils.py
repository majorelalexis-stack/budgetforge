"""Log-safe helpers for PII."""


def mask_email(email: str) -> str:
    """Pseudonymise un email pour les logs.

    alice@example.com -> ali***@example.com
    bob@x.io          -> bob***@x.io
    a@example.com     -> a***@example.com
    ''                -> ''
    invalide          -> '***'
    """
    if not email:
        return ""
    if "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    if not local or not domain:
        return "***"
    prefix = local[:3] if len(local) >= 3 else local
    return f"{prefix}***@{domain}"
