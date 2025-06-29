"""
Test script for AI Agent application
"""

import asyncio
import httpx
from database import db
from ollama_client import ollama

async def test_database():
    """Test database connection"""
    print("Testing database connection...")
    try:
        success = db.test_connection()
        if success:
            print("✅ Database connection successful")
            
            # Test query
            results = db.execute_query("SELECT COUNT(*) as count FROM JOBORDER")
            print(f"✅ JOBORDER table has {results[0]['count']} records")
            
            # Test schema
            schema = db.get_table_schema()
            print(f"✅ JOBORDER table has {len(schema)} columns")
            
        else:
            print("❌ Database connection failed")
    except Exception as e:
        print(f"❌ Database test failed: {e}")

async def test_ollama():
    """Test Ollama connection"""
    print("\nTesting Ollama connection...")
    try:
        healthy = await ollama.is_healthy()
        if healthy:
            print("✅ Ollama connection successful")
        else:
            print("❌ Ollama connection failed")
    except Exception as e:
        print(f"❌ Ollama test failed: {e}")

async def test_api_endpoints():
    """Test FastAPI endpoints"""
    print("\nTesting API endpoints...")
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        try:
            # Test root endpoint
            response = await client.get(f"{base_url}/")
            if response.status_code == 200:
                print("✅ Root endpoint working")
            else:
                print("❌ Root endpoint failed")
                
        except Exception as e:
            print(f"❌ API endpoint test failed: {e}")
            print("Make sure FastAPI server is running: uvicorn main:app --reload")

async def test_sample_queries():
    """Test sample natural language queries"""
    print("\nTesting sample queries...")
    
    sample_questions = [
        "Show all Local parts",
        "แสดงชิ้นส่วนที่มี stock น้อยกว่า 1000",
        "What are the Foam parts?",
        "รายการ SKD Accessory"
    ]
    
    for question in sample_questions:
        print(f"\nQuestion: {question}")
        try:
            # This would normally go through the API
            # For now, just test the components
            schema = """
Table: JOBORDER
Columns: MAT_TYPE, MAT_GROUP, SAP_ID, PART_NO, PART_NAME, STOCK_MAIN, etc.
            """
            
            sql, explanation = await ollama.generate_sql(question, schema)
            print(f"SQL: {sql}")
            print(f"Explanation: {explanation}")
            
        except Exception as e:
            print(f"❌ Query test failed: {e}")

async def main():
    """Run all tests"""
    print("🚀 Starting AI Agent Tests\n")
    
    await test_database()
    await test_ollama()
    await test_api_endpoints()
    
    # Only test sample queries if Ollama is working
    try:
        healthy = await ollama.is_healthy()
        if healthy:
            await test_sample_queries()
        else:
            print("\n⚠️ Skipping query tests - Ollama not available")
    except:
        print("\n⚠️ Skipping query tests - Ollama not available")
    
    print("\n✅ Tests completed!")

if __name__ == "__main__":
    asyncio.run(main())