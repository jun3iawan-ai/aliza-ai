from crewai import Task, Crew
from core.agent import aliza_agent
from core.tool_router import detect_intent


def ask_aliza(user_input: str) -> str:

    intent = detect_intent(user_input)

    # =========================
    # SEARCH INTENT
    # =========================
    if intent == "search":

        task_description = f"""
Gunakan internet search untuk menemukan informasi terbaru
dan jawab pertanyaan berikut berdasarkan hasil pencarian.

Pertanyaan:
{user_input}

Pastikan jawaban menggunakan informasi paling terbaru.
"""

    # =========================
    # MATH INTENT
    # =========================
    elif intent == "math":

        task_description = f"""
Hitung atau selesaikan soal matematika berikut:

{user_input}

Berikan hasil yang benar.
"""

    # =========================
    # DEFAULT CHAT
    # =========================
    else:

        task_description = f"""
Jawab pertanyaan pengguna berikut dengan jelas:

{user_input}
"""

    task = Task(
        description=task_description,
        expected_output="Jawaban yang jelas dan akurat.",
        agent=aliza_agent
    )

    crew = Crew(
        agents=[aliza_agent],
        tasks=[task],
        verbose=False
    )

    result = crew.kickoff()

    return str(result)