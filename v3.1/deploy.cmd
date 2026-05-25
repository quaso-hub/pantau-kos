@echo off
echo === GOD EYE Deploy ===

set PROJECT_ID=kos-monitor
set REGION=asia-southeast1
set SERVICE=god-eye

gcloud run deploy %SERVICE% ^
  --source . ^
  --region %REGION% ^
  --platform managed ^
  --allow-unauthenticated ^
  --set-env-vars="TELEGRAM_TOKEN=%TELEGRAM_TOKEN%,GEMINI_API_KEY=%GEMINI_API_KEY%,MAPS_API_KEY=%MAPS_API_KEY%,DEEPSEEK_API_KEY=%DEEPSEEK_API_KEY%,ALLOWED_CHAT_ID=%ALLOWED_CHAT_ID%,GOOGLE_CLOUD_PROJECT=%PROJECT_ID%,N8N_WEBHOOK_SECRET=%N8N_WEBHOOK_SECRET%" ^
  --memory 512Mi ^
  --timeout 120 ^
  --service-account god-eye-sa@%PROJECT_ID%.iam.gserviceaccount.com

echo.
echo Set webhook:
echo curl "https://api.telegram.org/bot%TELEGRAM_TOKEN%/setWebhook?url=https://%SERVICE%-134668262767.%REGION%.run.app/webhook"
