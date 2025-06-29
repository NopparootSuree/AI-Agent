"""
Main entry point for AI Agent
"""

import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# Import the main app
from app.main import app

if __name__ == "__main__":
    import uvicorn
    # Use string import for reload functionality
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)