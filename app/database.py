"""
Database connection and operations for AI Agent
"""

import pyodbc
import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class DatabaseConnection:
    def __init__(self):
        self.server = os.getenv("DB_SERVER", "sqlserver")  # Use Docker service name
        self.port = os.getenv("DB_PORT", "1433")           # Use internal port  
        self.database = os.getenv("DB_NAME", "JOBORDER")
        self.username = os.getenv("DB_USER", "sa")
        self.password = os.getenv("DB_PASSWORD", "Snc@min123")
        
        self.connection_string = f"""
            DRIVER={{ODBC Driver 18 for SQL Server}};
            SERVER={self.server},{self.port};
            DATABASE={self.database};
            UID={self.username};
            PWD={self.password};
            TrustServerCertificate=yes;
        """
    
    def get_connection(self):
        """Create and return database connection"""
        try:
            conn = pyodbc.connect(self.connection_string)
            return conn
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    def execute_query(self, query: str) -> List[Dict[str, Any]]:
        """Execute SELECT query and return results as list of dictionaries"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(query)
            columns = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                row_dict = {}
                for i, value in enumerate(row):
                    row_dict[columns[i]] = value
                results.append(row_dict)
            
            return results
            
        finally:
            cursor.close()
            conn.close()
    
    def get_table_schema(self, table_name: str = "JOBORDER") -> List[Dict[str, Any]]:
        """Get table schema information"""
        query = f"""
            SELECT 
                COLUMN_NAME,
                DATA_TYPE,
                IS_NULLABLE,
                COLUMN_DEFAULT,
                CHARACTER_MAXIMUM_LENGTH
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME = '{table_name}'
            ORDER BY ORDINAL_POSITION
        """
        
        return self.execute_query(query)

# Global database instance
db = DatabaseConnection()