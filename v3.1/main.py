#!/usr/bin/env python3
"""
GOD EYE — Main entry point
Baca CLAUDE.md untuk arsitektur lengkap.
"""
import os, logging, asyncio
from flask import Flask, request, jsonify
from telegram import Update, Bot
from telegram.constants import ParseMode

from bot.handlers import handle_update
from monitor.receiver import handle_monitor_post

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("god-eye")

app = Flask(__name__)

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
ALLOWED_CHAT_ID  = int(os.environ["ALLOWED_CHAT_ID"])
N8N_SECRET       = os.environ.get("N8N_WEBHOOK_SECRET", "")

bot = Bot(token=TELEGRAM_TOKEN)


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json(force=True)
    asyncio.run(handle_update(data, bot, ALLOWED_CHAT_ID))
    return jsonify({"ok": True})


@app.route("/monitor", methods=["POST"])
def n8n_monitor():
    """Endpoint untuk n8n kirim listing baru."""
    # Verify secret
    if N8N_SECRET and request.headers.get("X-Secret") != N8N_SECRET:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(force=True)
    asyncio.run(handle_monitor_post(data, bot, ALLOWED_CHAT_ID))
    return jsonify({"ok": True})


@app.route("/", methods=["GET"])
def health():
    return "GOD EYE — online", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    log.info(f"Starting God Eye on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
