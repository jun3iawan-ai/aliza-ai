import os

ACTIVE_FILE = "memory/active_document.txt"


def set_active_document(path):

    os.makedirs("memory", exist_ok=True)

    with open(ACTIVE_FILE, "w", encoding="utf-8") as f:
        f.write(path)


def get_active_document():

    if not os.path.exists(ACTIVE_FILE):
        return None

    with open(ACTIVE_FILE, "r", encoding="utf-8") as f:
        path = f.read().strip()

    if os.path.exists(path):
        return path

    return None