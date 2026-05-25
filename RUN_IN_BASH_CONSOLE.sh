#!/bin/bash
# KOST-BOT PYTHONANYWHERE DEPLOYMENT SCRIPT
# Copy-paste commands satu per satu di Bash console

# ============================================
# STEP 1: Clone Repository
# ============================================
cd ~
git clone https://github.com/quaso-hub/pantau-kos.git kost-bot
cd kost-bot
pwd
ls -la main.py

# ============================================
# STEP 2: Create Virtual Environment
# ============================================
mkvirtualenv --python=/usr/bin/python3.11 kos_bot

# ============================================
# STEP 3: Install Dependencies
# ============================================
workon kos_bot
pip install --upgrade pip
pip install -r ~/kost-bot/requirements.txt

# ============================================
# STEP 4: Verify Installation
# ============================================
pip list | grep -E "flask|asyncpg|telegram"

# ============================================
# DONE!
# Now go to Web tab and:
# 1. Update WSGI file (see WSGI_CONTENT.py)
# 2. Set Virtualenv path: /home/sadas/.virtualenvs/kos_bot
# 3. Set Working directory: /home/sadas/kost-bot
# 4. Add Environment variables
# 5. Click Reload
# ============================================
