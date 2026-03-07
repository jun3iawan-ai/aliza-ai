import os
import importlib


def load_skills():

    skills = []

    folder = "skills_custom"

    if not os.path.exists(folder):
        return skills

    for file in os.listdir(folder):

        if file.endswith(".py") and not file.startswith("_"):

            module_name = file[:-3]

            module = importlib.import_module(f"skills_custom.{module_name}")

            if hasattr(module, "tool"):

                skills.append(module.tool)

    return skills