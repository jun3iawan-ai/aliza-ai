async function loadBTC(){

try{

let res = await fetch('/api/market/btc')

if(!res.ok){
throw new Error("API error")
}

let data = await res.json()

// =========================
// PRICE
// =========================

let price=data.price ?? 0
document.getElementById("price").innerText="$"+price.toLocaleString()

// =========================
// RSI
// =========================

let rsi=data.rsi ?? "-"
let rsiEl=document.getElementById("rsi")

rsiEl.innerText=rsi

if(rsi<30){
rsiEl.style.color="#22c55e"
}
else if(rsi>70){
rsiEl.style.color="#ef4444"
}
else{
rsiEl.style.color="#f59e0b"
}

// =========================
// FEAR GREED
// =========================

let fear=data.fear_greed ?? "-"
let fearEl=document.getElementById("fear")

fearEl.innerText=fear

if(fear<20){
fearEl.style.color="#ef4444"
}
else if(fear<50){
fearEl.style.color="#f59e0b"
}
else{
fearEl.style.color="#22c55e"
}

// =========================
// DOMINANCE
// =========================

let dom=data.dominance ?? "-"
document.getElementById("dom").innerText=dom+"%"

// =========================
// MARKET SCORE
// =========================

let score=data.market_score ?? 0

document.getElementById("score").innerText=score
document.getElementById("score-fill").style.width=score+"%"

// =========================
// TREND
// =========================

let trend=data.trend ?? "-"
let trendEl=document.getElementById("trend")

trendEl.innerText=trend

if(trend=="BULLISH"){
trendEl.style.color="#22c55e"
}
else if(trend=="BEARISH"){
trendEl.style.color="#ef4444"
}
else{
trendEl.style.color="#f59e0b"
}

// =========================
// CYCLE
// =========================

document.getElementById("cycle").innerText=data.cycle_phase ?? "-"

// =========================
// WHALE ACTIVITY
// =========================

let whale=data.whale_activity ?? "-"
let whaleEl=document.getElementById("whale")

whaleEl.innerText=whale

if(whale=="ACCUMULATING"){
whaleEl.style.color="#22c55e"
}

// =========================
// MARKET INTELLIGENCE
// =========================

let bottom=data.bottom_probability ?? 0
let alt=data.altseason_probability ?? 0
let crash=data.crash_probability ?? 0

let bottomEl=document.getElementById("bottom")
let altEl=document.getElementById("alt")
let crashProbEl=document.getElementById("crash_prob")

bottomEl.innerText=bottom+"%"
altEl.innerText=alt+"%"
crashProbEl.innerText=crash+"%"

if(bottom>60){
bottomEl.style.color="#22c55e"
}

if(alt>60){
altEl.style.color="#22c55e"
}

if(crash>50){
crashProbEl.style.color="#ef4444"
}

// =========================
// CRASH ALERT
// =========================

let crashAlert=data.crash_alert ?? "-"
let crashEl=document.getElementById("crash")

crashEl.innerText=crashAlert

if(crashAlert=="EXTREME"){
crashEl.style.color="#ef4444"
}
else if(crashAlert=="HIGH"){
crashEl.style.color="#f97316"
}
else if(crashAlert=="MEDIUM"){
crashEl.style.color="#f59e0b"
}
else if(crashAlert=="LOW"){
crashEl.style.color="#22c55e"
}

// =========================
// SIGNAL
// =========================

let signal=data.signal ?? "HOLD"
let el=document.getElementById("signal")

if(signal=="BUY"){
el.className="signal signal-buy"
el.innerText="BUY ZONE"
}
else if(signal=="SELL"){
el.className="signal signal-sell"
el.innerText="SELL ZONE"
}
else{
el.className="signal signal-hold"
el.innerText="HOLD"
}

// =========================
// TRADING BRAIN
// =========================

if(data.trade_setup){

let trade=data.trade_setup

document.getElementById("setup").innerText=trade.setup ?? "-"

document.getElementById("entry").innerText="$"+(trade.entry ?? "-")

document.getElementById("sl").innerText="$"+(trade.sl ?? "-")

document.getElementById("tp").innerText="$"+(trade.tp1 ?? "-")

document.getElementById("rr").innerText=trade.risk_reward ?? "-"

}

// =========================
// ANALYSIS
// =========================

document.getElementById("analysis").innerText=data.analysis ?? "-"

// =========================
// UPDATE TIME
// =========================

document.getElementById("updated").innerText=
"Last Updated: "+new Date().toLocaleString()

}catch(e){

console.log("BTC terminal error",e)

}

}

// =========================
// INITIAL LOAD
// =========================

loadBTC()

// =========================
// AUTO REFRESH
// =========================

setInterval(loadBTC,60000)
