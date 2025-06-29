"""
Startup script for AI Agent FastAPI server
"""

import uvicorn
import os
import sys
import time
import subprocess
from pathlib import Path

def check_dependencies():
    """Check if required services are running"""
    print("🔍 Checking dependencies...")
    
    # Check SQL Server
    try:
        result = subprocess.run([
            "docker", "exec", "ai-agent-sqlserver", 
            "/opt/mssql-tools18/bin/sqlcmd", 
            "-S", "localhost", 
            "-U", "sa", 
            "-P", "Snc@min123", 
            "-C", 
            "-Q", "SELECT 1"
        ], capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            print("✅ SQL Server is running")
        else:
            print("❌ SQL Server is not responding")
            return False
            
    except Exception as e:
        print(f"❌ SQL Server check failed: {e}")
        return False
    
    # Check if Ollama container exists (it might be downloading)
    try:
        result = subprocess.run([
            "docker", "ps", "-a", "--filter", "name=ai-agent-ollama", "--format", "{{.Status}}"
        ], capture_output=True, text=True)
        
        if "Up" in result.stdout:
            print("✅ Ollama container is running")
        elif result.stdout.strip():
            print("⚠️ Ollama container exists but not running")
        else:
            print("⚠️ Ollama container not found")
            
    except Exception as e:
        print(f"⚠️ Ollama check failed: {e}")
    
    return True

def main():
    """Main startup function"""
    print("🚀 Starting AI Agent Server\n")
    
    # Check if we're in the right directory
    project_root = Path(__file__).parent.parent
    if not (project_root / "main.py").exists():
        print("❌ main.py not found. Please run from the project directory.")
        sys.exit(1)
    
    # Change to project root directory
    os.chdir(project_root)
    
    # Check dependencies
    if not check_dependencies():
        print("\n❌ Required dependencies are not running.")
        print("Please ensure Docker containers are running:")
        print("  docker compose up -d sqlserver")
        print("  docker compose up -d ollama")
        sys.exit(1)
    
    # Set environment variables
    os.environ["DB_SERVER"] = "localhost"
    os.environ["DB_PORT"] = "1436"
    os.environ["DB_NAME"] = "JOBORDER"
    os.environ["DB_USER"] = "sa"
    os.environ["DB_PASSWORD"] = "Snc@min123"
    os.environ["OLLAMA_URL"] = "http://localhost:11434"
    os.environ["OLLAMA_MODEL"] = "qwen3:8b"
    
    print("\n🌟 Starting FastAPI server...")
    print("📍 Server will be available at: http://localhost:8000")
    print("📖 API documentation at: http://localhost:8000/docs")
    print("🏥 Health check at: http://localhost:8000/health")
    print("\n" + "="*50)
    
    # Start the server
    try:
        # Add current directory to Python path for imports
        sys.path.insert(0, str(project_root))
        
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Server failed to start: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()