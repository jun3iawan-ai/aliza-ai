#!/bin/bash

BOT_TOKEN="ISI_BOT_TOKEN_ANDA"
CHAT_ID="ISI_CHAT_ID_ANDA"

send_alert () {
curl -s -X POST https://api.telegram.org/bot$BOT_TOKEN/sendMessage \
-d chat_id=$CHAT_ID \
-d text="$1"
}

# cek API service
if ! systemctl is-active --quiet aliza-api; then
send_alert "⚠️ AlizaAI ALERT: API service DOWN!"
sudo systemctl restart aliza-api
fi

# cek Telegram bot
if ! systemctl is-active --quiet aliza-telegram; then
send_alert "⚠️ AlizaAI ALERT: Telegram bot DOWN!"
sudo systemctl restart aliza-telegram
fi

# cek disk
DISK=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')

if [ $DISK -gt 85 ]; then
send_alert "⚠️ AlizaAI ALERT: Disk usage ${DISK}%"
fi

# cek RAM
RAM=$(free | awk '/Mem:/ {printf("%.0f"), $3/$2 * 100}')

if [ $RAM -gt 85 ]; then
send_alert "⚠️ AlizaAI ALERT: RAM usage ${RAM}%"
fi
