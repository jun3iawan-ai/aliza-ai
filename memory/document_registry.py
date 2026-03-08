import json
import os
from datetime import datetime

REGISTRY_FILE = "memory/documents.json"


def register_document(file_name):

    if not os.path.exists(REGISTRY_FILE):
        data = []
    else:
        with open(REGISTRY_FILE) as f:
            data = json.load(f)

    data.append({
        "file": file_name,
        "uploaded": datetime.now().isoformat()
    })

    with open(REGISTRY_FILE, "w") as f:
        json.dump(data, f, indent=2)