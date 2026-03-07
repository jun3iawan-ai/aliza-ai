const chatbox = document.getElementById("chatbox")
const input = document.getElementById("messageInput")


// =======================
// SEND MESSAGE
// =======================

async function sendMessage(){

const message = input.value.trim()

if(message === "") return

addMessage("user", message)

input.value = ""

showTyping()

try{

const res = await fetch("/chat",{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify({
message: message
})
})

const data = await res.json()

removeTyping()

if(data.response){

addMessage("ai", data.response)

}else{

addMessage("ai","Terjadi kesalahan.")

}

}catch(err){

removeTyping()

addMessage("ai","Server tidak merespon.")

}

}


// =======================
// ADD MESSAGE
// =======================

function addMessage(role, text){

const div = document.createElement("div")

div.classList.add("message", role)

div.innerText = text

chatbox.appendChild(div)

chatbox.scrollTop = chatbox.scrollHeight

}


// =======================
// TYPING INDICATOR
// =======================

function showTyping(){

const div = document.createElement("div")

div.id = "typing"

div.classList.add("message","ai")

div.innerText = "Aliza sedang mengetik..."

chatbox.appendChild(div)

chatbox.scrollTop = chatbox.scrollHeight

}

function removeTyping(){

const typing = document.getElementById("typing")

if(typing) typing.remove()

}


// =======================
// CLEAR CHAT
// =======================

function clearChat(){

chatbox.innerHTML = ""

}


// =======================
// UPLOAD FILE
// =======================

async function uploadFile(){

const fileInput = document.getElementById("fileUpload")

const file = fileInput.files[0]

if(!file) return

addMessage("user","Mengupload dokumen: " + file.name)

const formData = new FormData()

formData.append("file", file)

addMessage("ai","Memproses dokumen...")

try{

const res = await fetch("/upload",{
method:"POST",
body:formData
})

const data = await res.json()

if(data.summary){

addMessage("ai","Ringkasan dokumen:\n\n" + data.summary)

}else{

addMessage("ai","Gagal memproses dokumen.")

}

}catch(err){

addMessage("ai","Upload gagal.")

}

}


// =======================
// ENTER KEY SEND
// =======================

input.addEventListener("keypress", function(e){

if(e.key === "Enter"){

sendMessage()

}

})