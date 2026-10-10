#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "🚀 Starting Deployment of AI Voice Platform..."

# 1. Pull the latest code before building
echo "📦 Pulling latest changes from Git..."
git pull origin main

# 2. Deploy the Main AI Platform Stack (infrastructure/docker/docker-compose.yml)
echo "🧠 Deploying Main AI Platform (Database, API, Frontend, Nginx)..."
cd infrastructure/docker
docker compose up -d --build
cd ../../

echo "✅ Deployment Successful! Here are your running containers:"
docker ps
