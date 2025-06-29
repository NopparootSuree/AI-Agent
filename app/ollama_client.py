"""
Ollama client for AI Agent
"""

import httpx
import os
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

class OllamaClient:
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_MODEL", "qwen3:8b")
        self.timeout = 30.0
    
    async def is_healthy(self) -> bool:
        """Check if Ollama service is healthy"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False
    
    async def generate_sql(self, question: str, schema: str) -> Tuple[str, str]:
        """Generate SQL query from natural language question"""
        
        prompt = f"""You are an AI that generates safe SQL SELECT queries for a Microsoft SQL Server database.

{schema}

Rules:
1. Generate ONLY SELECT queries - NO INSERT, UPDATE, DELETE, DROP, ALTER commands
2. Use only the JOBORDER table
3. Return clean, readable SQL syntax
4. Handle both Thai and English questions
5. Provide a clear explanation of what the query does

User question: {question}

Please respond in this exact format:
SQL:
[Your SQL query here]

EXPLANATION:
[Your explanation here]

Example:
User: "Show parts with stock less than 100"
SQL:
SELECT PART_NO, PART_NAME, STOCK_MAIN
FROM JOBORDER
WHERE STOCK_MAIN < 100;

EXPLANATION:
This query selects part numbers, part names, and main stock quantities for all parts where the main stock is less than 100 units.
"""

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False
                    },
                    timeout=self.timeout
                )
                
            if response.status_code == 200:
                result = response.json()
                ai_response = result.get("response", "")
                
                # Parse SQL and explanation
                sql_query, explanation = self._parse_response(ai_response)
                return sql_query, explanation
            else:
                raise Exception(f"Ollama API returned status {response.status_code}")
                
        except Exception as e:
            logger.error(f"Ollama generate SQL failed: {e}")
            raise
    
    def _parse_response(self, response: str) -> Tuple[str, str]:
        """Parse AI response to extract SQL and explanation"""
        try:
            # Method 1: Look for SQL: and EXPLANATION: markers
            if "SQL:" in response and "EXPLANATION:" in response:
                parts = response.split("EXPLANATION:")
                sql_part = parts[0].replace("SQL:", "").strip()
                explanation_part = parts[1].strip()
                
                # Clean up SQL
                sql_lines = []
                for line in sql_part.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('```') and not line.startswith('sql'):
                        sql_lines.append(line)
                
                sql_query = '\n'.join(sql_lines).strip()
                
                return sql_query, explanation_part
            
            # Method 2: Look for code blocks
            elif "```sql" in response.lower():
                lines = response.split('\n')
                sql_lines = []
                explanation_lines = []
                in_sql_block = False
                
                for line in lines:
                    if "```sql" in line.lower():
                        in_sql_block = True
                        continue
                    elif "```" in line and in_sql_block:
                        in_sql_block = False
                        continue
                    elif in_sql_block:
                        sql_lines.append(line)
                    elif not in_sql_block and line.strip():
                        explanation_lines.append(line)
                
                sql_query = '\n'.join(sql_lines).strip()
                explanation = '\n'.join(explanation_lines).strip()
                
                return sql_query, explanation
            
            # Method 3: Fallback - try to identify SQL by keywords
            else:
                lines = response.split('\n')
                sql_lines = []
                explanation_lines = []
                
                for line in lines:
                    line_upper = line.strip().upper()
                    if any(keyword in line_upper for keyword in ['SELECT', 'FROM', 'WHERE', 'ORDER BY', 'GROUP BY']):
                        sql_lines.append(line.strip())
                    elif line.strip() and not any(marker in line.upper() for marker in ['SQL:', 'EXPLANATION:', '```']):
                        explanation_lines.append(line.strip())
                
                sql_query = '\n'.join(sql_lines).strip()
                explanation = '\n'.join(explanation_lines).strip()
                
                return sql_query, explanation if explanation else "Query executed successfully"
                
        except Exception as e:
            logger.error(f"Failed to parse AI response: {e}")
            # Return the original response as both SQL and explanation
            return response.strip(), "AI response parsing failed"

# Global Ollama client instance
ollama = OllamaClient()