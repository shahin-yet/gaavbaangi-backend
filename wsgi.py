#!/usr/bin/env python3
"""
WSGI configuration for PythonAnywhere deployment
"""

import sys
import os

# Add the project directory to Python path
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.append(project_dir)

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Import the Flask app
from app import app as application