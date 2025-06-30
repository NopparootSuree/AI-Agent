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
    
    logger.info(f"Starting clean_sql_syntax with: {sql}")
    
    
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
    
    # Auto-fix VARCHAR CAST issues for numeric operations
    numeric_columns = ['PRD_QTY', 'QTY_REQ', 'QTY_RECEIVED', 'PD_REQ', 'REQ_PART',
                      'STOCK_MAIN', 'STOCK_NG', 'STOCK_SAFETY']
    
    # Fix SUM/AVG/MAX/MIN operations on VARCHAR columns
    for col in numeric_columns:
        # Fix SUM(column) -> SUM(CAST(column AS FLOAT))
        sql = re.sub(rf'\bSUM\({col}\)', f'SUM(CAST({col} AS FLOAT))', sql, flags=re.IGNORECASE)
        sql = re.sub(rf'\bAVG\({col}\)', f'AVG(CAST({col} AS FLOAT))', sql, flags=re.IGNORECASE)
        sql = re.sub(rf'\bMAX\({col}\)', f'MAX(CAST({col} AS FLOAT))', sql, flags=re.IGNORECASE)
        sql = re.sub(rf'\bMIN\({col}\)', f'MIN(CAST({col} AS FLOAT))', sql, flags=re.IGNORECASE)
        
        # Fix comparison operations: column > value -> CAST(column AS FLOAT) > value
        sql = re.sub(rf'\b{col}\s*([><=!]+)\s*(\d+)', f'CAST({col} AS FLOAT) \\1 \\2', sql, flags=re.IGNORECASE)
        
        # Fix comparison between two columns: col1 < col2 -> CAST(col1 AS FLOAT) < CAST(col2 AS FLOAT)
        for col2 in numeric_columns:
            if col != col2:
                sql = re.sub(rf'\b{col}\s*([><=!]+)\s*{col2}\b', 
                           f'CAST({col} AS FLOAT) \\1 CAST({col2} AS FLOAT)', sql, flags=re.IGNORECASE)
    
    # Fix arithmetic with CAST columns in SELECT with GROUP BY
    logger.info(f"Before GROUP BY arithmetic fix: {sql}")
    
    if 'GROUP BY' in sql.upper():
        # Find expressions with CAST operations mixed with aggregates
        select_part = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
        if select_part:
            select_content = select_part.group(1)
            
            # Check for patterns like: CAST(col AS FLOAT) - SUM(CAST(col2 AS FLOAT))
            mixed_pattern = re.search(r'(PART_NO),\s*(CAST\s*\([^)]+\)\s*[-+*/]\s*(SUM|AVG|COUNT|MAX|MIN)\s*\([^)]+\).*?)\s+AS\s+(\w+)', select_content, re.IGNORECASE)
            if mixed_pattern:
                expression = mixed_pattern.group(2)
                alias = mixed_pattern.group(4)
                # Convert CAST(col AS FLOAT) - SUM(...) to SUM(CAST(col AS FLOAT)) - SUM(...)
                new_expression = re.sub(r'CAST\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s+AS\s+FLOAT\s*\)\s*([-+*/])\s*(SUM|AVG|COUNT|MAX|MIN)', 
                                      r'SUM(CAST(\1 AS FLOAT)) \2 \3', expression, flags=re.IGNORECASE)
                sql = sql.replace(mixed_pattern.group(0), f'PART_NO, {new_expression} AS {alias}')
                logger.info(f"Fixed mixed CAST-aggregate expression: {new_expression}")
            
            # Check if there are multiple CAST operations without aggregates  
            cast_count = len(re.findall(r'CAST\s*\([^)]+\)', select_content, re.IGNORECASE))
            agg_count = len(re.findall(r'\b(SUM|AVG|COUNT|MAX|MIN)\s*\(', select_content, re.IGNORECASE))
            
            logger.info(f"CAST count: {cast_count}, Aggregate count: {agg_count}")
            
            if cast_count >= 2 and agg_count == 0:
                # Wrap the entire arithmetic expression in SUM()
                expr_match = re.search(r'(PART_NO),\s*(.+?)\s+AS\s+(\w+)', select_content, re.IGNORECASE)
                if expr_match:
                    expression = expr_match.group(2)
                    alias = expr_match.group(3)
                    new_expression = f'SUM({expression})'
                    sql = sql.replace(expr_match.group(0), f'PART_NO, {new_expression} AS {alias}')
                    logger.info(f"Wrapped expression in SUM: {new_expression}")
    
    logger.info(f"After GROUP BY arithmetic fix: {sql}")
    
    # Fix GROUP BY clause - ensure all non-aggregate columns are in GROUP BY
    logger.info(f"Checking for GROUP BY in: {sql.upper()}")
    logger.info(f"GROUP BY found: {'GROUP BY' in sql.upper()}")
    if 'GROUP BY' in sql.upper():
        logger.info(f"Fixing GROUP BY for SQL: {sql}")
        
        # Extract all individual column names from the entire SQL
        # Find all CAST(column_name AS TYPE) patterns
        all_columns = set()
        cast_columns = re.findall(r'CAST\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s+AS\s+\w+\)', sql, re.IGNORECASE)
        for col in cast_columns:
            all_columns.add(col)
            logger.info(f"Found CAST column: {col}")
        
        # Also find direct column references
        direct_columns = re.findall(r'\b([A-Z_][A-Z0-9_]{2,})\b', sql)
        joborder_columns = {'PART_NO', 'PART_NAME', 'SAP_ID', 'MAT_TYPE', 'MAT_GROUP', 
                           'PRD_QTY', 'QTY_REQ', 'QTY_RECEIVED', 'PD_REQ', 'REQ_PART',
                           'STOCK_MAIN', 'STOCK_NG', 'STOCK_SAFETY'}
        
        for col in direct_columns:
            if col in joborder_columns:
                all_columns.add(col)
                logger.info(f"Found direct column: {col}")
        
        logger.info(f"All columns found: {all_columns}")
        
        # Find existing GROUP BY columns
        group_by_match = re.search(r'GROUP\s+BY\s+(.+?)(?:\s+ORDER\s+BY|\s+HAVING|\s*$)', sql, re.IGNORECASE | re.DOTALL)
        if group_by_match:
            existing_group_by_text = group_by_match.group(1).strip()
            existing_group_by = set()
            for col in existing_group_by_text.split(','):
                col = col.strip()
                if '.' in col:
                    col = col.split('.')[-1]
                existing_group_by.add(col)
            
            logger.info(f"Existing GROUP BY: {existing_group_by}")
            
            # Exclude columns that are in aggregate functions from GROUP BY requirement
            select_part = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
            if select_part:
                select_text = select_part.group(1)
                # Find columns that are wrapped in aggregate functions
                agg_wrapped = re.findall(r'\b(SUM|AVG|COUNT|MAX|MIN)\s*\(\s*CAST\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)', select_text, re.IGNORECASE)
                agg_columns = {col[1] for col in agg_wrapped}
                logger.info(f"Columns in aggregates: {agg_columns}")
                
                # Columns that need to be in GROUP BY (not in aggregates)
                need_group_by = all_columns - agg_columns - existing_group_by
                logger.info(f"Columns needing GROUP BY: {need_group_by}")
                
                if need_group_by:
                    # Add missing columns to GROUP BY
                    new_group_by = existing_group_by_text + ', ' + ', '.join(sorted(need_group_by))
                    sql = sql.replace(group_by_match.group(0), f'GROUP BY {new_group_by}')
                    logger.info(f"Updated SQL: {sql}")
    
    # Fix missing closing parentheses for aggregate functions
    logger.info(f"Before parentheses fix: {sql}")
    
    # Fix pattern: SUM(CAST(...) AS FLOAT) FROM -> SUM(CAST(...) AS FLOAT)) FROM
    # Count opening and closing parentheses after SUM/AVG/COUNT/MAX/MIN
    agg_functions = ['SUM', 'AVG', 'COUNT', 'MAX', 'MIN']
    for func in agg_functions:
        pattern = rf'\b{func}\s*\('
        matches = list(re.finditer(pattern, sql, re.IGNORECASE))
        for match in matches:
            start_pos = match.end() - 1  # Position of opening parenthesis
            open_count = 0
            close_count = 0
            
            # Count parentheses from the opening parenthesis to end of SELECT clause
            from_pos = sql.upper().find(' FROM', start_pos)
            if from_pos == -1:
                continue
                
            search_text = sql[start_pos:from_pos]
            for char in search_text:
                if char == '(':
                    open_count += 1
                elif char == ')':
                    close_count += 1
            
            # If we have unmatched opening parentheses, add closing ones
            if open_count > close_count:
                missing_closes = ')' * (open_count - close_count)
                sql = sql[:from_pos] + missing_closes + sql[from_pos:]
                logger.info(f"Added {open_count - close_count} closing parentheses for {func}")
    
    logger.info(f"After parentheses fix: {sql}")
    
    # Clean up extra spaces and newlines
    sql = re.sub(r'\s+', ' ', sql).strip()
    
    return sql

# FastAPI app
app = FastAPI(
    title="Manufacturing Production Management AI Assistant",
    description="AI-powered assistant for analyzing production orders, inventory levels, and material requirements in manufacturing operations. Converts natural language questions to SQL queries for the JOBORDER production management system.",
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
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

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
    ai_response: Optional[str] = None
    timestamp: datetime

class HealthResponse(BaseModel):
    status: str
    database: str
    ollama: str
    timestamp: datetime

class SchemaResponse(BaseModel):
    table_name: str
    columns: List[dict]


# JOBORDER table schema for Store → Production Line Material Management
JOBORDER_SCHEMA = """
STORE → PRODUCTION LINE MATERIAL MANAGEMENT DATABASE

Table: JOBORDER (Material Flow Tracking: Store → Production Line)

ALL COLUMNS ARE VARCHAR(50) IN CURRENT DATABASE:

IDENTIFICATION FIELDS (VARCHAR - NO MATH OPERATIONS):
- MAT_TYPE - Material sourcing: 'Local' (domestic) or 'SKD' (imported)
- MAT_GROUP - Part category: 'Foam' (cushioning) or 'Accessory' (components)
- SAP_ID - SAP ERP material code identifier
- PART_NO - Unique part number for tracking
- PART_NAME - Descriptive part name

PRODUCTION DEMAND TRACKING (VARCHAR - USE CAST TO CONVERT FOR MATH):
- PRD_QTY - Production line order quantity (how much line ordered from store)
- QTY_REQ - Total parts required for production (total demand from line)
- QTY_RECEIVED - Parts already delivered from store to production line
- PD_REQ - Production department additional part requests
- REQ_PART - Additional emergency part requirements

STORE INVENTORY STATUS (VARCHAR - USE CAST TO CONVERT FOR MATH):
- STOCK_MAIN - Store on-hand inventory (available to send to production)
- STOCK_NG - Defective parts in store (cannot send to line, need QC)
- STOCK_SAFETY - Safety stock buffer maintained in store

MATERIAL FLOW EXAMPLES:
- Store has 1000 STOCK_MAIN, Production needs 500 QTY_REQ → Can deliver 500 to line
- Production ordered 800 PRD_QTY, but only received 200 QTY_RECEIVED → Still need 600
- STOCK_NG > 0 means store has defective parts that cannot be sent to production
- STOCK_SAFETY maintains buffer stock for unexpected demand spikes
- REQ_PART tracks emergency additional requirements beyond normal demand
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
    
    prompt = f"""You are an AI for a manufacturing factory's production system. Generate SQL queries for production data analysis.

SYSTEM: JOBORDER table tracks production orders, materials, and inventory.

KEY COLUMNS FOR STORE → PRODUCTION LINE TRACKING:
- MAT_TYPE: 'Local'/'SKD' (material sourcing type)
- MAT_GROUP: 'Foam'/'Accessory' (part category)  
- SAP_ID: SAP ERP material code identifier
- PART_NO, PART_NAME: Part identification
- PRD_QTY: Production line order quantity (how much production line ordered)
- QTY_REQ: Total required parts for production (total demand from line)
- QTY_RECEIVED: Parts already delivered to production line
- PD_REQ: Production department additional requests
- REQ_PART: Additional emergency part requirements
- STOCK_MAIN: Store inventory on-hand (available to send)
- STOCK_NG: Defective parts in store (cannot send to line)
- STOCK_SAFETY: Safety stock buffer in store

CRITICAL SQL RULES:
1. SELECT queries only
2. SQL Server syntax (no backticks, use TOP not LIMIT)
3. JOBORDER table only
4. ALL numeric fields are stored as VARCHAR - must use CAST(field AS FLOAT) for math operations
5. Use CAST(column AS FLOAT) before SUM/AVG/MAX/MIN/comparison operations
6. Only MAT_TYPE, MAT_GROUP, SAP_ID, PART_NO, PART_NAME are pure text (no casting needed)
7. Numeric fields requiring CAST: PRD_QTY, QTY_REQ, QTY_RECEIVED, PD_REQ, REQ_PART, STOCK_MAIN, STOCK_NG, STOCK_SAFETY
8. GROUP BY rule: ALL non-aggregate columns in SELECT must be in GROUP BY clause

CORRECT EXAMPLES:
✓ SELECT * FROM JOBORDER WHERE CAST(STOCK_MAIN AS FLOAT) < 100
✓ SELECT COUNT(*) FROM JOBORDER WHERE CAST(STOCK_NG AS FLOAT) > 0  
✓ SELECT SUM(CAST(QTY_REQ AS FLOAT)) FROM JOBORDER WHERE MAT_GROUP = 'Foam'
✓ SELECT PART_NO, CAST(STOCK_MAIN AS FLOAT) - CAST(QTY_REQ AS FLOAT) AS BALANCE FROM JOBORDER
✓ SELECT MAT_TYPE, SUM(CAST(STOCK_SAFETY AS FLOAT)) FROM JOBORDER GROUP BY MAT_TYPE
✓ SELECT PART_NO, MAT_TYPE, SUM(CAST(QTY_REQ AS FLOAT)) FROM JOBORDER GROUP BY PART_NO, MAT_TYPE

WRONG EXAMPLES - DO NOT DO:
✗ SELECT SUM(STOCK_MAIN) FROM JOBORDER (need CAST AS FLOAT)
✗ SELECT PRD_QTY + QTY_REQ FROM JOBORDER (need CAST AS FLOAT)
✗ SELECT STOCK_MAIN > STOCK_SAFETY FROM JOBORDER (need CAST AS FLOAT)
✗ SELECT PART_NO, SUM(CAST(QTY_REQ AS FLOAT)) FROM JOBORDER GROUP BY MAT_TYPE (PART_NO not in GROUP BY)
✗ SELECT MAT_TYPE, PART_NO, COUNT(*) FROM JOBORDER GROUP BY MAT_TYPE (missing PART_NO in GROUP BY)

User question: {question}

Respond as:
SQL: [query]
EXPLANATION: [brief manufacturing context]"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=60.0
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
                logger.info(f"About to call clean_sql_syntax")
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
                logger.info(f"About to call clean_sql_syntax (fallback)")
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

async def generate_ai_response(question: str, results: List[dict], language: str = "auto") -> str:
    """Generate AI response interpreting SQL results for MM (Material Management) phase"""
    
    # Detect language
    lang_instruction = ""
    if language == "thai" or (language == "auto" and any(ord(c) > 3584 and ord(c) < 3711 for c in question)):
        lang_instruction = "ตอบเป็นภาษาไทย ใช้คำศัพท์การผลิตและการจัดการวัตถุดิบ"
    else:
        lang_instruction = "Answer in English using manufacturing and material management terminology"
    
    # Prepare detailed results analysis for AI
    if not results:
        results_text = "ไม่พบข้อมูล - อาจต้องตรวจสอบเงื่อนไขการค้นหา"
        analysis_data = "No data to analyze"
    else:
        results_count = len(results)
        analysis_data = ""
        
        # Detailed analysis for different query types
        if results_count == 1 and len(results[0]) == 1:
            first_key, first_value = next(iter(results[0].items()))
            if 'count' in first_key.lower() or 'total' in first_key.lower() or 'sum' in first_key.lower():
                results_text = f"ผลลัพธ์: {first_key} = {first_value:,.2f}"
                
                # Add specific analysis based on the metric
                if 'stock' in first_key.lower():
                    if float(first_value) > 100000:
                        analysis_data = f"สต็อกระดับสูง ({first_value:,.0f}) - เพียงพอสำหรับการผลิตต่อเนื่อง"
                    elif float(first_value) > 10000:
                        analysis_data = f"สต็อกระดับปกติ ({first_value:,.0f}) - ควรติดตามการใช้งาน"
                    else:
                        analysis_data = f"สต็อกระดับต่ำ ({first_value:,.0f}) - ต้องวางแผนสั่งซื้อเร่งด่วน"
                elif 'qty' in first_key.lower():
                    analysis_data = f"ปริมาณรวม {first_value:,.0f} หน่วย - วิเคราะห์สำหรับการวางแผนการผลิต"
            else:
                results_text = f"พบข้อมูล 1 รายการ:\n{first_key}: {first_value}"
                analysis_data = "ข้อมูลเฉพาะรายการ - ต้องการการวิเคราะห์เพิ่มเติม"
        elif results_count <= 20:
            # Show detailed results for each part with store→line analysis
            results_text = f"รายการ Parts ทั้งหมด {results_count} รายการ:\n\n"
            pending_delivery = []
            completed_delivery = []
            
            for i, row in enumerate(results, 1):
                part_no = row.get('PART_NO', 'Unknown')
                part_name = row.get('PART_NAME', '')
                
                # Extract key values for analysis
                stock_main = float(row.get('STOCK_MAIN', 0)) if row.get('STOCK_MAIN') else 0
                qty_req = float(row.get('QTY_REQ', 0)) if row.get('QTY_REQ') else 0
                qty_received = float(row.get('QTY_RECEIVED', 0)) if row.get('QTY_RECEIVED') else 0
                pending_qty = qty_req - qty_received if qty_req > 0 else 0
                
                # Format each part details
                results_text += f"Part {i}: {part_no}\n"
                results_text += f"  ชื่อ: {part_name[:50]}{'...' if len(part_name) > 50 else ''}\n"
                results_text += f"  ไลน์ร้องขอ: {qty_req:,.0f} หน่วย\n"
                results_text += f"  ส่งแล้ว: {qty_received:,.0f} หน่วย\n"
                results_text += f"  ยังต้องส่ง: {pending_qty:,.0f} หน่วย\n"
                results_text += f"  สต็อกคลัง: {stock_main:,.0f} หน่วย\n"
                
                # Status analysis
                if pending_qty > 0:
                    if stock_main >= pending_qty:
                        status = "✅ พร้อมส่ง"
                        completed_delivery.append(part_no)
                    else:
                        status = f"⚠️ สต็อกไม่พอ (ขาด {pending_qty - stock_main:,.0f})"
                        pending_delivery.append(f"{part_no} (ขาด {pending_qty - stock_main:,.0f})")
                else:
                    status = "✅ ส่งครบแล้ว"
                    completed_delivery.append(part_no)
                
                results_text += f"  สถานะ: {status}\n\n"
            
            # Summary analysis
            if pending_delivery:
                analysis_data = f"รายการรอส่ง: {len(pending_delivery)} parts - {', '.join(pending_delivery[:3])}"
                if len(pending_delivery) > 3:
                    analysis_data += f" และอีก {len(pending_delivery)-3} รายการ"
            else:
                analysis_data = f"ส่งครบแล้ว: {results_count} parts ทั้งหมด"
        else:
            # Large dataset summary with key insights
            results_text = f"พบข้อมูล {results_count} รายการ\n"
            
            # Calculate key metrics from the data
            total_stock = 0
            low_stock_count = 0
            ng_items = 0
            
            for row in results[:20]:  # Analyze first 20 records
                try:
                    stock_main = float(row.get('STOCK_MAIN', 0)) if row.get('STOCK_MAIN') else 0
                    stock_ng = float(row.get('STOCK_NG', 0)) if row.get('STOCK_NG') else 0
                    
                    total_stock += stock_main
                    if stock_main < 1000:
                        low_stock_count += 1
                    if stock_ng > 0:
                        ng_items += 1
                except:
                    pass
            
            # Show sample data
            results_text += "ตัวอย่างข้อมูล 3 รายการแรก:\n"
            for i, row in enumerate(results[:3], 1):
                results_text += f"{i}. "
                for key, value in row.items():
                    if key in ['PART_NO', 'PART_NAME', 'MAT_TYPE', 'SAP_ID']:
                        results_text += f"{key}: {value}, "
                results_text = results_text.rstrip(', ') + "\n"
            
            analysis_data = f"สรุป: สต็อกรวม ~{total_stock:,.0f}, รายการสต็อกต่ำ {low_stock_count} รายการ, รายการ NG {ng_items} รายการ"
    
    prompt = f"""คุณเป็น AI ผู้เชี่ยวชาญด้าน Store → Production Line Material Management

คำถาม: "{question}"
ข้อมูลที่พบ: {results_text}
การวิเคราะห์: {analysis_data}

ระบบ Store → Production Line:
- STOCK_MAIN: สต็อกในคลัง (พร้อมส่งไลน์ผลิต)
- STOCK_NG: ของเสียในคลัง (ส่งไลน์ไม่ได้)
- STOCK_SAFETY: สต็อกสำรองในคลัง
- QTY_REQ: ไลน์ผลิตร้องขอทั้งหมด
- QTY_RECEIVED: ส่งให้ไลน์ผลิตแล้ว
- PRD_QTY: ไลน์ผลิตสั่งจากคลัง
- PD_REQ: แผนกผลิตร้องขอเพิ่ม
- REQ_PART: ความต้องการฉุกเฉิน

บทบาทคุณ:
1. ตอบแบบคำพูดสั้นๆ เป็นมิตร
2. สรุปผลลัพธ์ที่สำคัญ
3. ใช้ภาษาพูดง่ายๆ
4. {lang_instruction}

รูปแบบการตอบ:
พบ [ตัวเลข] รายการครับ/ค่ะ แต่ละ part มี [สรุปสั้นๆ] 
ที่สำคัญคือ [point หลัก]
แนะนำให้ [การดำเนินการสั้นๆ]

ตอบแบบเพื่อนร่วมงานที่พูดสั้น กะทัดรัด เป็นมิตร ไม่เป็นทางการ"""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=60.0
            )
            
        if response.status_code == 200:
            result = response.json()
            ai_response = result.get("response", "").strip()
            return ai_response
        else:
            return "Unable to generate AI response at this time."
            
    except Exception as e:
        logger.error(f"AI response generation failed: {str(e)}")
        logger.error(f"Exception type: {type(e)}")
        return f"AI response failed: {str(e)[:100]}"

# API Endpoints

@app.get("/", response_model=dict)
async def root():
    """Root endpoint"""
    return {
        "message": "Manufacturing Production Management AI Assistant",
        "description": "AI-powered system for production data analysis and inventory management",
        "version": "1.0.0",
        "capabilities": [
            "Production order analysis",
            "Inventory level monitoring", 
            "Material requirement planning",
            "Quality control tracking",
            "Supply chain insights"
        ]
    }

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
        
        # Generate AI response interpreting the results
        ai_response = await generate_ai_response(request.question, results, request.language)
        
        return QueryResponse(
            question=request.question,
            sql_query=sql_query,
            explanation=explanation,
            results=results,
            ai_response=ai_response,
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