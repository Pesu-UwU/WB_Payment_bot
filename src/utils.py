def extract_surname(full_name: str) -> str:
    parts = [p for p in full_name.strip().split() if p]
    return parts[-1] if parts else "Клиент"

def make_spreadsheet_title(surname: str) -> str:
    return f"ИП {surname} Автоответчик"

def make_admin_name(surname: str) -> str:
    return f"IP {surname}"

def safe_strip(s: str) -> str:
    return (s or "").strip()
