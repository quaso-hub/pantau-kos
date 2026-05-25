"""
PythonAnywhere WSGI Configuration for kost-bot
This file should be placed at /var/www/sadas_pythonanywhere_com_wsgi.py
Or copied into the WSGI configuration section in PythonAnywhere Web tab
"""

import sys
import os
import asyncio
from pathlib import Path

# Add the project directory to the path
project_home = os.path.expanduser('~/kost-bot')
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Set working directory
os.chdir(project_home)

# Import and setup logging BEFORE importing the app
from infrastructure.logger import setup_logging
setup_logging()

# Import the Flask app from main.py
from main import app as application

# The 'application' variable is what PythonAnywhere looks for
# It will call application(environ, start_response) for each request
