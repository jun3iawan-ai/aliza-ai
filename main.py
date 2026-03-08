from dotenv import load_dotenv
load_dotenv()

from crewai import Task, Crew
from core.agent import aliza_agent
from memory.memory_manager import (
    add_message,
    get_context,
    save_user_info,
    get_user_name
)
from core.tool_router import detect_intent

print("AlizaAI siap digunakan")
print("Ketik 'exit' untuk keluar\n")

while True:
    try:
        user = input("User: ").strip()

        if user.lower() in ["exit", "quit"]:
            print("AlizaAI dihentikan.")
            break

        # simpan percakapan user
        add_message("User", user)

        # =========================
        # MEMORY SYSTEM
        # =========================

        name = save_user_info(user)

        if name:
            response = f"Baik, saya ingat. Nama Anda {name.title()}."

        elif "siapa nama saya" in user.lower():

            stored_name = get_user_name()

            if stored_name:
                response = f"Nama Anda {stored_name.title()}."
            else:
                response = "Maaf, saya belum tahu nama Anda."

        else:

            # =========================
            # TOOL ROUTER
            # =========================

            intent = detect_intent(user)

            context = get_context()

            task_description = f"""
Gunakan konteks percakapan berikut:

{context}

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

        # simpan jawaban AI
        add_message("Aliza", str(response))

        print(f"\nAliza: {response}\n")

    except KeyboardInterrupt:
        print("\n\nAlizaAI dihentikan oleh pengguna.")
        break

    except Exception as e:
        print(f"\nTerjadi kesalahan: {e}\n")