// =======================
// WAIT DOM READY
// =======================

document.addEventListener("DOMContentLoaded", () => {

const input = document.getElementById("messageInput");
const chatbox = document.getElementById("chatbox");


// =======================
// SEND MESSAGE
// =======================

async function sendMessage() {

    const message = input.value.trim();

    if (!message) return;

    addMessage("user", message);

    input.value = "";

    showTyping();

    input.disabled = true;

    try {

        const res = await fetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message,
                channel: "web"
            })
        });

        if (!res.ok) {
            throw new Error("Server error");
        }

        const data = await res.json();

        removeTyping();

        addMessage("ai", data.answer || "Terjadi kesalahan pada server.");

    } catch (err) {

        removeTyping();

        console.error("API ERROR:", err);

        addMessage("ai", "Server tidak merespon.");

    }

    input.disabled = false;
    input.focus();
}


// =======================
// ADD MESSAGE
// =======================

function addMessage(role, text) {

    const div = document.createElement("div");

    div.classList.add("message", role);

    div.textContent = text;

    chatbox.appendChild(div);

    chatbox.scrollTop = chatbox.scrollHeight;
}


// =======================
// TYPING INDICATOR
// =======================

function showTyping() {

    const div = document.createElement("div");

    div.id = "typing";

    div.classList.add("message", "ai");

    div.textContent = "Aliza sedang mengetik...";

    chatbox.appendChild(div);

    chatbox.scrollTop = chatbox.scrollHeight;
}

function removeTyping() {

    const typing = document.getElementById("typing");

    if (typing) typing.remove();
}


// =======================
// CLEAR CHAT
// =======================

window.clearChat = function() {
    chatbox.innerHTML = "";
}


// =======================
// ENTER KEY SEND
// =======================

input.addEventListener("keydown", function(e) {

    if (e.key === "Enter") {

        e.preventDefault();

        sendMessage();
    }

});


// =======================
// UPLOAD FILE (placeholder)
// =======================

window.uploadFile = function() {
    alert("Fitur upload dokumen belum diaktifkan.");
}

});