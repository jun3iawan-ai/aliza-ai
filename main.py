from dotenv import load_dotenv
load_dotenv()

from crewai import Task, Crew
from core.agent import aliza_agent
from core.tool_router import detect_intent

print("AlizaAI siap digunakan")
print("Ketik 'exit' untuk keluar\n")

while True:

    try:

        user = input("User: ").strip()

        if user.lower() in ["exit", "quit"]:
            print("AlizaAI dihentikan.")
            break

        # =========================
        # TOOL ROUTER
        # =========================

        intent = detect_intent(user)

        task_description = f"""
Intent pengguna: {intent}

Jawab pertanyaan berikut dengan tepat:

{user}

Jika intent adalah 'search', gunakan internet search.
Jika intent adalah 'chat', jawab langsung tanpa tool.
"""

        task = Task(
            description=task_description,
            expected_output="Jawaban yang jelas dan informatif.",
            agent=aliza_agent
        )

        crew = Crew(
            agents=[aliza_agent],
            tasks=[task],
            verbose=False
        )

        response = crew.kickoff()

        print(f"\nAliza: {response}\n")

    except KeyboardInterrupt:

        print("\n\nAlizaAI dihentikan oleh pengguna.")
        break

    except Exception as e:

        print(f"\nTerjadi kesalahan: {e}\n")