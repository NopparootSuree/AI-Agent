"""
AI Agent for SQL Query Generation
FastAPI application that converts natural language questions to SQL queries
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import httpx
import pyodbc
import os
from datetime import datetime
import logging
import re

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_sql_syntax(sql: str) -> str:
    """Clean common SQL syntax errors for SQL Server compatibility"""
    if not sql:
        return sql
    
    
    # Remove markdown code blocks
    sql = re.sub(r'```sql\s*', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'```\s*', '', sql)
    sql = re.sub(r'^\s*sql\s*', '', sql, flags=re.IGNORECASE)  # Remove stray 'sql' keywords
    
    # Remove all backticks completely
    sql = re.sub(r'`([^`]+)`', r'\1', sql)  # Replace `column` with column
    sql = sql.replace('`', '')  # Remove any remaining backticks
    
    # Replace MySQL/PostgreSQL functions with SQL Server equivalents
    replacements = {
        'DATETIME()': 'GETDATE()',
        'NOW()': 'GETDATE()',
        'CURDATE()': 'CAST(GETDATE() AS DATE)',
        'LENGTH(': 'LEN(',
        'SUBSTR(': 'SUBSTRING(',
    }
    
    for mysql_func, sqlserver_func in replacements.items():
        sql = sql.replace(mysql_func, sqlserver_func)
    
    # Handle LIMIT -> TOP conversion (both LIMIT n and LIMIT offset, n)
    limit_match = re.search(r'\bLIMIT\s+(?:(\d+),\s*)?(\d+)\b', sql, re.IGNORECASE)
    if limit_match:
        offset = limit_match.group(1)
        limit_num = limit_match.group(2)
        
        # Remove LIMIT clause completely
        sql = re.sub(r'\s+LIMIT\s+(?:\d+,\s*)?\d+\b', '', sql, flags=re.IGNORECASE)
        
        # Add TOP after SELECT (ignore offset for now as SQL Server TOP doesn't directly support it)
        if offset is None or offset == '0':
            sql = re.sub(r'\bSELECT\b', f'SELECT TOP {limit_num}', sql, flags=re.IGNORECASE)
        else:
            # For offset queries, we'll use OFFSET/FETCH instead
            sql = re.sub(r'\bSELECT\b', f'SELECT TOP {limit_num}', sql, flags=re.IGNORECASE)
            # Note: Full OFFSET/FETCH implementation would need ORDER BY
    
    # Clean up extra spaces and newlines
    sql = re.sub(r'\s+', ' ', sql).strip()
    
    return sql

# FastAPI app
app = FastAPI(
    title="AI Agent SQL Query Generator",
    description="Convert natural language questions to SQL queries for JOBORDER table",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration  
DB_SERVER = os.getenv("DB_SERVER", "sqlserver")  # Use Docker service name
DB_PORT = os.getenv("DB_PORT", "1433")           # Use internal port
DB_NAME = os.getenv("DB_NAME", "JOBORDER")
DB_USER = os.getenv("DB_USER", "sa")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Snc@min123")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://172.19.0.2:11434")  # Use direct IP
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")

# Database connection string
CONNECTION_STRING = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={DB_SERVER},{DB_PORT};DATABASE={DB_NAME};UID={DB_USER};PWD={DB_PASSWORD};TrustServerCertificate=yes;"

# Request/Response models
class QueryRequest(BaseModel):
    question: str
    language: Optional[str] = "auto"  # "thai", "english", or "auto"

class QueryResponse(BaseModel):
    question: str
    sql_query: str
    explanation: str
    results: Optional[List[dict]] = None
    timestamp: datetime

class HealthResponse(BaseModel):
    status: str
    database: str
    ollama: str
    timestamp: datetime

class SchemaResponse(BaseModel):
    table_name: str
    columns: List[dict]

# JOBORDER table schema for prompt
JOBORDER_SCHEMA = """
Table: JOBORDER

Columns:
- MAT_TYPE (VARCHAR) - material type (e.g., 'Local', 'SKD')
- MAT_GROUP (VARCHAR) - material group (e.g., 'Foam', 'Accessory/fitting')
- SAP_ID (VARCHAR) - SAP material code (e.g., '10030059', '20004212')
- PART_NO (VARCHAR) - part number (e.g., '16320300000732')
- PART_NAME (VARCHAR) - part name (e.g., '16320300000732 Top foam')
- PRD_QTY (INT) - production quantity
- QTY_BOM (DECIMAL) - BOM quantity
- QTY_REQ (INT) - required quantity
- QTY_RECEIVED (INT) - quantity already received
- PD_REQ (INT) - production requested quantity
- PD01, PD02, PD04, PD09 (INT) - planned dispatch quantities by department
- WIP_QTY (INT) - work in progress quantity
- REQ_PART (INT) - requested part quantity
- STOCK_MAIN (INT) - main stock
- STOCK_NG (INT) - defect stock
- STOCK_UNPACK (INT) - unpacked stock
- STOCK_SAFETY (INT) - safety stock

Sample data examples:
- Local Foam parts: Top foam, Volute shell with high STOCK_MAIN quantities
- SKD Accessory/fitting: ADHESIVE, service cards, trademarks with STOCK_UNPACK quantities
"""

def get_db_connection():
    """Get database connection"""
    try:
        conn = pyodbc.connect(CONNECTION_STRING)
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")

async def generate_sql_with_ollama(question: str) -> tuple[str, str]:
    """Generate SQL query using Ollama"""
    
    prompt = f"""You are an AI that generates safe SQL SELECT queries for Microsoft SQL Server.

{JOBORDER_SCHEMA}

CRITICAL SQL Server Rules:
1. Generate ONLY SELECT queries - NO INSERT, UPDATE, DELETE, DROP, ALTER commands
2. Use only the JOBORDER table
3. DO NOT use backticks (`) - SQL Server does NOT support them
4. Use square brackets [column_name] or plain column names only
5. Use single quotes (') for string values
6. Use ONLY SQL Server functions: GETDATE(), DATEADD(), DATEDIFF(), LEN(), SUBSTRING()
7. DO NOT use MySQL functions: DATETIME(), NOW(), CURDATE(), LENGTH(), SUBSTR()
8. DO NOT use PostgreSQL syntax
9. All columns must be from JOBORDER table only

Correct SQL Server Examples:
✓ SELECT * FROM JOBORDER WHERE MAT_TYPE = 'Local'
✓ SELECT [PART_NO], [PART_NAME] FROM JOBORDER
✓ SELECT TOP 10 * FROM JOBORDER
✓ WHERE CREATED_AT >= GETDATE()
✓ WHERE LEN(PART_NO) > 5

WRONG Examples (DO NOT USE):
✗ SELECT `PART_NO` FROM JOBORDER (no backticks)
✗ WHERE DATETIME() (no MySQL functions)
✗ LIMIT 10 (use TOP instead)

User question: {question}

Please respond in this exact format:
SQL:
[Your SQL query here]

EXPLANATION:
[Your explanation here]
"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30.0
            )
            
        if response.status_code == 200:
            result = response.json()
            ai_response = result.get("response", "")
            logger.info(f"Full AI response: {ai_response}")
            
            # Parse SQL and explanation from response
            if "SQL:" in ai_response and "EXPLANATION:" in ai_response:
                parts = ai_response.split("EXPLANATION:")
                sql_part = parts[0].replace("SQL:", "").strip()
                explanation_part = parts[1].strip()
                
                # Clean up SQL - remove common syntax errors
                logger.info(f"Raw SQL from AI: {sql_part}")
                sql_part = clean_sql_syntax(sql_part)
                logger.info(f"Cleaned SQL: {sql_part}")
                
                return sql_part, explanation_part
            else:
                # Fallback parsing - AI didn't use our expected format
                # Look for SQL in code blocks or after keywords
                sql_query = ""
                explanation = ""
                
                # Try to extract SQL from markdown code blocks
                sql_match = re.search(r'```sql\s*(.*?)\s*```', ai_response, re.DOTALL | re.IGNORECASE)
                if sql_match:
                    sql_query = sql_match.group(1).strip()
                else:
                    # Try to find SQL after "SQL:" keyword
                    sql_match = re.search(r'SQL:\s*(.*?)(?=\n\n|\Z)', ai_response, re.DOTALL | re.IGNORECASE)
                    if sql_match:
                        sql_query = sql_match.group(1).strip()
                
                # Get explanation from remaining text
                if sql_query:
                    # Remove the SQL part and markdown from explanation
                    explanation = ai_response
                    if sql_match:
                        explanation = explanation.replace(sql_match.group(0), "").strip()
                    explanation = re.sub(r'```sql.*?```', '', explanation, flags=re.DOTALL | re.IGNORECASE)
                    explanation = explanation.strip()
                
                # Clean up SQL
                logger.info(f"Raw SQL from AI (fallback): {sql_query}")
                sql_query = clean_sql_syntax(sql_query)
                logger.info(f"Cleaned SQL (fallback): {sql_query}")
                
                return sql_query, explanation
                
        else:
            raise HTTPException(status_code=500, detail="Failed to generate SQL with Ollama")
            
    except Exception as e:
        logger.error(f"Ollama request failed: {e}")
        raise HTTPException(status_code=500, detail=f"AI service unavailable: {e}")

def execute_sql_query(sql_query: str) -> List[dict]:
    """Execute SQL query and return results"""
    
    # Basic SQL injection prevention
    sql_upper = sql_query.upper().strip()
    dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'ALTER', 'TRUNCATE', 'CREATE']
    
    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            raise HTTPException(status_code=400, detail=f"Dangerous SQL keyword detected: {keyword}")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(sql_query)
        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            row_dict = {}
            for i, value in enumerate(row):
                row_dict[columns[i]] = value
            results.append(row_dict)
        
        cursor.close()
        conn.close()
        
        return results
        
    except Exception as e:
        logger.error(f"SQL execution failed: {e}")
        raise HTTPException(status_code=400, detail=f"SQL execution failed: {e}")

# API Endpoints

@app.get("/", response_model=dict)
async def root():
    """Root endpoint"""
    return {"message": "AI Agent SQL Query Generator", "version": "1.0.0"}

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    
    # Check database
    db_status = "ok"
    try:
        conn = get_db_connection()
        conn.close()
    except:
        db_status = "error"
    
    # Check Ollama
    ollama_status = "ok"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
            if response.status_code != 200:
                ollama_status = "error"
    except:
        ollama_status = "error"
    
    overall_status = "ok" if db_status == "ok" and ollama_status == "ok" else "error"
    
    return HealthResponse(
        status=overall_status,
        database=db_status,
        ollama=ollama_status,
        timestamp=datetime.now()
    )

@app.get("/schema", response_model=SchemaResponse)
async def get_schema():
    """Get JOBORDER table schema"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COLUMN_NAME,
                DATA_TYPE,
                IS_NULLABLE,
                COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = 'JOBORDER'
            ORDER BY ORDINAL_POSITION
        """)
        
        columns = []
        for row in cursor.fetchall():
            columns.append({
                "name": row[0],
                "type": row[1],
                "nullable": row[2] == "YES",
                "default": row[3]
            })
        
        cursor.close()
        conn.close()
        
        return SchemaResponse(
            table_name="JOBORDER",
            columns=columns
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get schema: {e}")

@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """Process natural language question and return SQL query with results"""
    
    try:
        # Generate SQL query using Ollama
        sql_query, explanation = await generate_sql_with_ollama(request.question)
        
        # Execute SQL query
        results = execute_sql_query(sql_query)
        
        return QueryResponse(
            question=request.question,
            sql_query=sql_query,
            explanation=explanation,
            results=results,
            timestamp=datetime.now()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Query processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query processing failed: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)