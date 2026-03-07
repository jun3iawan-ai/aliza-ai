import json
import os

MEMORY_FOLDER = "memory/users"

os.makedirs(MEMORY_FOLDER, exist_ok=True)


def get_user_file(user_id):
    return os.path.join(MEMORY_FOLDER, f"{user_id}.json")


def load_user_memory(user_id):

    file_path = get_user_file(user_id)

    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)

    return {}


def save_user_memory(user_id, data):

    file_path = get_user_file(user_id)

    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


def save_user_name(user_id, text):

    text_lower = text.lower()

    if text_lower.startswith("nama saya"):

        name = text[9:].strip()

        if name:

            memory = load_user_memory(user_id)

            memory["name"] = name

            save_user_memory(user_id, memory)

            return name

    return None


def get_user_name(user_id):

    memory = load_user_memory(user_id)

    return memory.get("name")