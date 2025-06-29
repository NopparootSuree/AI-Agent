# AI Agent SQL Query Generator

AI Agent ที่แปลงคำถามภาษาธรรมชาติ (ไทย/อังกฤษ) เป็น SQL queries สำหรับตาราง JOBORDER

## 📁 Project Structure

```
AI-Agent/
├── app/                    # Main application code
│   ├── __init__.py
│   ├── main_with_mock.py   # FastAPI app with mock fallback
│   ├── main.py            # Original FastAPI app
│   ├── database.py        # Database connection module
│   ├── ollama_client.py   # Ollama client
│   └── mock_ollama.py     # Mock Ollama for testing
├── config/                # Configuration files
│   ├── .env              # Environment variables
│   └── requirements.txt  # Python dependencies
├── docker/               # Docker configuration
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── docker-compose.gpu.yml
│   └── docker-compose.simple.yml
├── scripts/              # Utility scripts
│   └── start_server.py   # Server startup script
├── sql/                  # SQL files
│   ├── init_database.sql # Database initialization
│   └── sample_data.sql   # Sample data
├── tests/                # Test files
│   ├── __init__.py
│   ├── simple_test.py    # Simple integration tests
│   └── test_app.py       # App tests
├── docs/                 # Documentation
│   ├── CLAUDE.md         # Claude Code guidance
│   └── TODO.md           # Project TODO list
├── venv/                 # Python virtual environment
└── main.py               # Main entry point
```

## 🚀 Quick Start

### 1. Start Infrastructure
```bash
# Option 1: Start services only (recommended)
docker compose -f docker/docker-compose.services-only.yml up -d

# Option 2: Start specific services
docker compose -f docker/docker-compose.yml up -d sqlserver
docker compose -f docker/docker-compose.yml up -d ollama

# Initialize database
sleep 10
docker cp sql/init_database.sql ai-agent-sqlserver:/tmp/init_database.sql
docker exec ai-agent-sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P 'Snc@min123' -C -i /tmp/init_database.sql
```

### 2. Setup Python Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r config/requirements.txt
```

### 3. Start Application
```bash
# Activate virtual environment
source venv/bin/activate

# Option 1: Direct run (recommended)
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Option 2: Simple run
python3 main.py

# Option 3: Using startup script (with dependency checks)
python3 scripts/start_server.py
```

### 4. Test API
```bash
# Health check
curl http://localhost:8000/health

# Natural language query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Show all Local parts"}'

# Thai language query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"แสดงชิ้นส่วนที่มี stock น้อยกว่า 1000"}'
```

## 📊 API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check
- `GET /schema` - JOBORDER table schema
- `POST /query` - Natural language to SQL query
- `GET /docs` - API documentation (Swagger UI)

## 🛠️ Technology Stack

- **Backend**: FastAPI + Python 3.10.12
- **Database**: Microsoft SQL Server 2019
- **AI Model**: Ollama + Qwen3:8b (with mock fallback)
- **Infrastructure**: Docker + WSL2
- **Environment**: Ubuntu 22.04

## 📋 JOBORDER Table Schema

Table มีข้อมูลเกี่ยวกับ:
- Material information (MAT_TYPE, MAT_GROUP, SAP_ID, PART_NO, PART_NAME)
- Production quantities (PRD_QTY, QTY_BOM, QTY_REQ, QTY_RECEIVED)
- Planning data (PD01, PD02, PD04, PD09, PD_REQ)
- Stock information (STOCK_MAIN, STOCK_NG, STOCK_UNPACK, STOCK_SAFETY)
- Work in progress (WIP_QTY, REQ_PART)

## 🧪 Testing

```bash
# Run simple tests
python3 tests/simple_test.py

# Run comprehensive tests
python3 tests/test_app.py
```

## 🔧 Troubleshooting

### Docker Build Issues
If you encounter Docker build errors (especially ODBC-related), use the services-only approach:

```bash
# Use services only (no Python container)
docker compose -f docker/docker-compose.services-only.yml up -d

# Run Python app locally
source venv/bin/activate
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Database Connection Issues
```bash
# Check if SQL Server is running
docker ps | grep sqlserver

# Test database connection
docker exec ai-agent-sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P 'Snc@min123' -C -Q "SELECT 1"

# Re-initialize database if needed
docker cp sql/init_database.sql ai-agent-sqlserver:/tmp/init_database.sql
docker exec ai-agent-sqlserver /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P 'Snc@min123' -C -i /tmp/init_database.sql
```

### Ollama Issues
The system has mock fallback for Ollama. If real Ollama is not available, it will automatically use mock responses.

## 📝 Development

See `docs/CLAUDE.md` for development guidelines and `docs/TODO.md` for project status.