#!/bin/bash

# GPU Setup Script for AI Agent
echo "🚀 Setting up AI Agent with GPU support..."

# Check if nvidia-docker is installed
if ! command -v nvidia-docker &> /dev/null; then
    echo "⚠️ nvidia-docker not found. Please install NVIDIA Container Toolkit first:"
    echo "https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
    exit 1
fi

# Check if GPU is available
if ! nvidia-smi &> /dev/null; then
    echo "⚠️ NVIDIA GPU not detected. Please check your drivers."
    exit 1
fi

echo "✅ GPU detected:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

# Stop existing containers
echo "🛑 Stopping existing containers..."
docker-compose -f docker-compose.with-ollama.yml down 2>/dev/null || true

# Start with GPU support
echo "🐳 Starting containers with GPU support..."
docker-compose -f docker-compose.gpu.yml up -d

# Wait for services to start
echo "⏳ Waiting for services to start..."
sleep 10

# Check if containers are running
echo "📊 Container status:"
docker-compose -f docker-compose.gpu.yml ps

# Install models
echo "🤖 Installing AI models..."
docker exec ai-agent-ollama ollama pull qwen2.5:7b
docker exec ai-agent-ollama ollama pull qwen2.5:3b

# Test GPU usage
echo "🔥 Testing GPU usage..."
docker exec ai-agent-ollama nvidia-smi

# Load sample data
echo "📊 Loading sample data..."
sleep 5
docker exec ai-agent-sqlserver /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "Snc@min123" -d JOBORDER -i /tmp/sample_data.sql

echo "✅ GPU setup complete!"
echo "🌐 Access the API at: http://localhost:8000"
echo "🔍 Test query: curl -X POST http://localhost:8000/query -H 'Content-Type: application/json' -d '{\"question\":\"มีกี่ part ทั้งหมด\"}'"