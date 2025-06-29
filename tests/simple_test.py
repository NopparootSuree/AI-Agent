"""
Simple test script without ODBC dependencies
"""

import asyncio
import httpx
import sys

# Test database connection using Docker exec
def test_database_via_docker():
    """Test database using docker exec"""
    import subprocess
    
    print("Testing database connection via Docker...")
    try:
        result = subprocess.run([
            "docker", "exec", "ai-agent-sqlserver", 
            "/opt/mssql-tools18/bin/sqlcmd", 
            "-S", "localhost", 
            "-U", "sa", 
            "-P", "Snc@min123", 
            "-C", 
            "-Q", "SELECT COUNT(*) FROM JOBORDER.dbo.JOBORDER"
        ], capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            print("✅ Database connection successful")
            print(f"✅ Query result: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ Database connection failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Database connection timeout")
        return False
    except Exception as e:
        print(f"❌ Database test error: {e}")
        return False

async def test_ollama():
    """Test Ollama connection"""
    print("\nTesting Ollama connection...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:11434/api/tags", timeout=5.0)
            if response.status_code == 200:
                result = response.json()
                models = result.get("models", [])
                print("✅ Ollama connection successful")
                print(f"✅ Available models: {len(models)}")
                for model in models:
                    print(f"   - {model.get('name', 'Unknown')}")
                return True
            else:
                print(f"❌ Ollama connection failed: HTTP {response.status_code}")
                return False
    except Exception as e:
        print(f"❌ Ollama test failed: {e}")
        return False

async def test_ollama_generate():
    """Test Ollama text generation"""
    print("\nTesting Ollama text generation...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "qwen3:8b",
                    "prompt": "Generate a simple SQL SELECT query to get all records from a table named JOBORDER",
                    "stream": False
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                result = response.json()
                ai_response = result.get("response", "")
                print("✅ Ollama text generation successful")
                print(f"✅ Response length: {len(ai_response)} characters")
                print(f"✅ Sample response: {ai_response[:200]}...")
                return True
            else:
                print(f"❌ Ollama generation failed: HTTP {response.status_code}")
                return False
                
    except Exception as e:
        print(f"❌ Ollama generation test failed: {e}")
        return False

def test_fastapi_basic():
    """Test basic FastAPI functionality"""
    print("\nTesting FastAPI basic functionality...")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        
        # Simple test app
        test_app = FastAPI()
        
        @test_app.get("/")
        def read_root():
            return {"message": "Hello World"}
        
        @test_app.get("/health")
        def health():
            return {"status": "ok"}
        
        client = TestClient(test_app)
        
        # Test endpoints
        response1 = client.get("/")
        response2 = client.get("/health")
        
        if response1.status_code == 200 and response2.status_code == 200:
            print("✅ FastAPI basic functionality working")
            return True
        else:
            print("❌ FastAPI basic functionality failed")
            return False
            
    except Exception as e:
        print(f"❌ FastAPI test failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("🚀 Starting AI Agent Simple Tests\n")
    
    tests_passed = 0
    total_tests = 4
    
    # Database test
    if test_database_via_docker():
        tests_passed += 1
    
    # Ollama tests
    if await test_ollama():
        tests_passed += 1
        
        # Only test generation if Ollama is working
        if await test_ollama_generate():
            tests_passed += 1
    else:
        print("⚠️ Skipping Ollama generation test - Ollama not available")
    
    # FastAPI test
    if test_fastapi_basic():
        tests_passed += 1
    
    print(f"\n📊 Test Results: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed!")
        return 0
    elif tests_passed >= 2:
        print("⚠️ Some tests failed, but core functionality seems to work")
        return 1
    else:
        print("❌ Many tests failed - check your setup")
        return 2

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)