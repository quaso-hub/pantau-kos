"""
COPY THIS EXACT CODE INTO /var/www/sadas_pythonanywhere_com_wsgi.py

Go to Web tab > WSGI configuration file > click the link
Delete semua isi, paste kode ini, click Save
"""

import sys
import os

# Add project directory
project_home = os.path.expanduser('~/kost-bot')
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Change directory
os.chdir(project_home)

# Setup logging
try:
    from infrastructure.logger import setup_logging
    setup_logging()
except Exception as e:
    print(f"Warning: Could not setup logging: {e}")

# Import Flask app
from main import app as application
