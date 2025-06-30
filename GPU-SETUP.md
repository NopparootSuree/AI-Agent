# GPU Setup Guide for AI Agent

## Prerequisites

### 1. Install NVIDIA Drivers
```bash
# Check if GPU is detected
nvidia-smi
```

### 2. Install NVIDIA Container Toolkit
```bash
# Ubuntu/Debian
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### 3. Configure Docker for GPU
```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

## GPU Setup

### Option 1: Automatic Setup
```bash
./setup-gpu.sh
```

### Option 2: Manual Setup
```bash
# Start with GPU support
docker-compose -f docker-compose.gpu.yml up -d

# Install models
docker exec ai-agent-ollama ollama pull qwen2.5:7b
docker exec ai-agent-ollama ollama pull qwen2.5:3b

# Load sample data
docker exec ai-agent-sqlserver /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "Snc@min123" -d JOBORDER -i /tmp/sample_data.sql
```

## Verify GPU Usage

### Check GPU in Ollama container
```bash
docker exec ai-agent-ollama nvidia-smi
```

### Monitor GPU usage during inference
```bash
watch -n 1 nvidia-smi
```

## Model Configuration

### GPU Models (Faster)
- `qwen2.5:7b` - Better accuracy, needs ~8GB VRAM
- `qwen2.5:3b` - Good balance, needs ~4GB VRAM  
- `qwen2.5:1.5b` - Fastest, needs ~2GB VRAM

### CPU Fallback Models
- `qwen2.5:1.5b` - Small model for low-end hardware

## Performance Comparison

| Model | CPU Time | GPU Time | VRAM | Accuracy |
|-------|----------|----------|------|----------|
| qwen2.5:1.5b | ~15s | ~2s | 2GB | Good |
| qwen2.5:3b | ~45s | ~5s | 4GB | Better |
| qwen2.5:7b | ~120s | ~8s | 8GB | Best |

## Troubleshooting

### GPU Not Detected
```bash
# Check NVIDIA drivers
nvidia-smi

# Check Docker GPU support
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
```

### Model Loading Issues
```bash
# Check Ollama logs
docker logs ai-agent-ollama

# Manually pull models
docker exec ai-agent-ollama ollama pull qwen2.5:3b
```

### Memory Issues
```bash
# Check GPU memory
nvidia-smi

# Use smaller model
docker-compose -f docker-compose.gpu.yml down
# Edit docker-compose.gpu.yml: change OLLAMA_MODEL to qwen2.5:1.5b
docker-compose -f docker-compose.gpu.yml up -d
```

## API Usage

Same as CPU version:
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"ยังมี part ใหนบ้าง ที่ยังไม่ได้ส่งครบตาม JobOrder"}'
```