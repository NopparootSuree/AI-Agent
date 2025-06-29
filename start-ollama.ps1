Write-Host "Starting Ollama with host binding..." -ForegroundColor Green

# Stop existing Ollama processes
Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force

# Set environment variable
$env:OLLAMA_HOST = "0.0.0.0:11434"

# Start Ollama
Write-Host "Setting OLLAMA_HOST to: $env:OLLAMA_HOST" -ForegroundColor Yellow
ollama serve