#!/usr/bin/env bash
set -euo pipefail

# Jalankan script ini dari root repo `kost-bot`.
# Tips: simpan secrets di file `.env` (lihat `.env.example`).

PROJECT_ID="${PROJECT_ID:-kos-monitor}"
REGION="${REGION:-asia-southeast1}"
SERVICE_NAME="${SERVICE_NAME:-kos-bot}"

# Auto-load .env bila ada (format: KEY=VALUE)
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

: "${TELEGRAM_TOKEN:?Harus di-set (env var atau .env)}"
: "${GEMINI_API_KEY:?Harus di-set (env var atau .env)}"
: "${MAPS_API_KEY:?Harus di-set (env var atau .env)}"
: "${DEEPSEEK_API_KEY:?Harus di-set (env var atau .env)}"
: "${ALLOWED_CHAT_ID:?Harus di-set (env var atau .env)}"

echo "Memulai proses deploy ke Google Cloud Run..."

gcloud run deploy "${SERVICE_NAME}" \
  --project "${PROJECT_ID}" \
  --source . \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars="TELEGRAM_TOKEN=${TELEGRAM_TOKEN},GEMINI_API_KEY=${GEMINI_API_KEY},MAPS_API_KEY=${MAPS_API_KEY},DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY},ALLOWED_CHAT_ID=${ALLOWED_CHAT_ID}" \
  --memory 512Mi \
  --timeout 120

echo ""
echo "Deploy selesai! Silakan copy URL yang muncul di atas."

# Setelah deploy, set webhook Telegram (opsional):
# SERVICE_URL="https://<service>-<hash>-<region>.a.run.app"
# curl "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook?url=${SERVICE_URL}/webhook"
