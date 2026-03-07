from crewai_tools import SerperDevTool
from crewai.tools import tool

from core.knowledge_base import search_knowledge
from core.skill_loader import load_skills


# =========================
# INTERNET SEARCH
# =========================
search_tool = SerperDevTool()


# =========================
# KNOWLEDGE SEARCH
# =========================
@tool("knowledge_search")
def knowledge_search_tool(query: str) -> str:
    """
    Search information from local knowledge documents.
    """
    return search_knowledge(query)


# =========================
# LOAD CUSTOM SKILLS
# =========================
custom_skills = load_skills()


# =========================
# REGISTER ALL TOOLS
# =========================
tools = [
    search_tool,
    knowledge_search_tool,
] + custom_skills