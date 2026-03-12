#!/bin/bash

cd /home/ubuntu/aliza-ai

echo "Pulling latest code..."
git pull origin main

echo "Restarting services..."
sudo systemctl restart aliza-api
sudo systemctl restart aliza-telegram

echo "Deploy completed"
