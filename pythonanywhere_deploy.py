#!/usr/bin/env python3
"""
PythonAnywhere Deployment Helper Script
Guides through the setup process with clear instructions
"""

import os
import sys
from pathlib import Path

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70 + "\n")

def main():
    print_section("KOST-BOT PYTHONANYWHERE DEPLOYMENT GUIDE")
    
    print("""
✅ Prerequisites Check:
   • PythonAnywhere account created: https://pythonanywhere.com (free tier)
   • GitHub repository: https://github.com/quaso-hub/pantau-kos
   • Neon PostgreSQL database: Already configured ✅
   
📋 Required Environment Variables (save these before starting):
   • DATABASE_URL=postgresql://neondb_owner:PASSWORD@HOST/neondb?sslmode=require
   • TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
   • GEMINI_API_KEY=YOUR_GEMINI_KEY
   • SUPABASE_URL=YOUR_SUPABASE_URL (if using)
   • SUPABASE_KEY=YOUR_SUPABASE_KEY (if using)
    """)
    
    print_section("STEP-BY-STEP DEPLOYMENT")
    
    steps = [
        ("LOGIN to PythonAnywhere", """
   1. Go to https://www.pythonanywhere.com
   2. Sign in with your account
   3. Go to the Dashboard
        """),
        
        ("CLONE GitHub Repository", """
   1. Open Bash console from PythonAnywhere dashboard
   2. Run these commands:
      
      cd ~
      git clone https://github.com/quaso-hub/pantau-kos.git kost-bot
      cd kost-bot
      ls -la
      
   3. Verify you see: main.py, requirements.txt, v2/ folder
        """),
        
        ("CREATE Python 3.11 Virtual Environment", """
   1. Still in Bash console, run:
      
      mkvirtualenv --python=/usr/bin/python3.11 kos_bot
      
   2. Wait for it to complete (takes 30-60 seconds)
   3. You should see: (kos_bot) user@server:~$
        """),
        
        ("INSTALL Required Packages", """
   1. Make sure you're in the virtual environment:
      
      workon kos_bot
      
   2. Install dependencies:
      
      pip install --upgrade pip
      pip install -r /home/USERNAME/kost-bot/requirements.txt
      
   3. This installs: flask, python-telegram-bot, asyncpg, google-cloud-firestore, etc
        """),
        
        ("CREATE Flask WSGI Configuration", """
   1. Go to Web tab in PythonAnywhere dashboard
   2. Click "Add a new web app"
   3. Choose "Manual configuration"
   4. Select "Python 3.11"
   5. Copy this code into WSGI file:
   
   --- START WSGI CODE ---
import sys
import os

# Set working directory
path = os.path.expanduser('~/kost-bot')
if path not in sys.path:
    sys.path.insert(0, path)

# Set environment variables (IMPORTANT!)
os.environ['DATABASE_URL'] = 'postgresql://neondb_owner:PASSWORD@HOST/neondb?sslmode=require'
os.environ['TELEGRAM_BOT_TOKEN'] = 'YOUR_BOT_TOKEN'
os.environ['GEMINI_API_KEY'] = 'YOUR_GEMINI_KEY'

# Import Flask app
from main import app as application
   --- END WSGI CODE ---
   
   6. Click "Save"
        """),
        
        ("CONFIGURE Web App Settings", """
   1. Go back to Web tab
   2. In "Virtualenv" section, enter:
      /home/USERNAME/.virtualenvs/kos_bot
   
   3. In "Working directory" section, enter:
      /home/USERNAME/kost-bot
   
   4. Scroll down to "Source code" and verify:
      /home/USERNAME/kost-bot
   
   5. Click "Reload" (green button at top)
        """),
        
        ("TEST Your Website", """
   1. Your site should be at: https://USERNAME.pythonanywhere.com
   2. Test endpoints:
      
      https://USERNAME.pythonanywhere.com/health
      Expected: {"status": "ok"}
      
      https://USERNAME.pythonanywhere.com/dashboard
      Expected: HTML dashboard page
   
   3. If 502 error or ImportError:
      - Check error log: Web tab > Error log
      - Verify virtualenv path is correct
      - Make sure DATABASE_URL is set
      - Click "Reload" again
        """),
        
        ("UPDATE Environment Variables", """
   1. Go to Account > Environment variables (top right)
   2. Add each variable:
      
      DATABASE_URL=postgresql://...
      TELEGRAM_BOT_TOKEN=...
      GEMINI_API_KEY=...
      etc
   
   3. Go back to Web tab and click "Reload"
        """),
        
        ("CONFIGURE Telegram Webhook", """
   1. Your webhook URL is: https://USERNAME.pythonanywhere.com/webhook
   2. Get your TELEGRAM_BOT_TOKEN from @BotFather
   3. Run this in local terminal:
      
      curl -X POST https://api.telegram.org/bot<TOKEN>/setWebhook \\
           -H "Content-Type: application/json" \\
           -d '{"url": "https://USERNAME.pythonanywhere.com/webhook"}'
   
   4. Expected response: {"ok": true, "result": true}
        """),
        
        ("VERIFY Integration", """
   1. Open Telegram
   2. Find your bot (@YourBotName)
   3. Send /start command
   4. Bot should respond with welcome message
   5. Check PythonAnywhere error log for any issues
        """),
    ]
    
    for i, (step_title, step_content) in enumerate(steps, 1):
        print(f"\n📌 STEP {i}: {step_title}")
        print(step_content)
        if i < len(steps):
            input("\n➜ Press ENTER when you've completed this step...")
    
    print_section("DEPLOYMENT COMPLETE! 🎉")
    print("""
✅ Your bot is now live!

📊 Status:
   • Website: https://USERNAME.pythonanywhere.com
   • Health endpoint: https://USERNAME.pythonanywhere.com/health
   • Dashboard: https://USERNAME.pythonanywhere.com/dashboard
   • Telegram bot: Active and listening for webhooks

🔧 If something goes wrong:
   1. Check PythonAnywhere error log: Web tab > Error log
   2. Check server log: Web tab > Server log
   3. Reload the web app
   4. Verify all environment variables are set
   5. Confirm DATABASE_URL is correct

📈 Next steps:
   1. Configure n8n to send data to /monitor endpoint
   2. Wait for n8n to start scraping
   3. Check /dashboard to see kos listings appearing

Need help? Check the error logs first!
    """)

if __name__ == "__main__":
    main()
