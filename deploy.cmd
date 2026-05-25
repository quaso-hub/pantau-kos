@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo Memulai proses deploy ke Google Cloud Run...

REM Default config (boleh dioverride via environment)
if "%PROJECT_ID%"==""   set "PROJECT_ID=kos-monitor"
if "%REGION%"==""       set "REGION=asia-southeast1"
if "%SERVICE_NAME%"=="" set "SERVICE_NAME=god-eye"

REM Auto-load .env bila ada (format: KEY=VALUE, abaikan baris kosong dan yang diawali #)
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    set "k=%%A"
    set "v=%%B"
    if not "!k!"=="" (
      if not "!k:~0,1!"=="#" (
        set "!k!=!v!"
      )
    )
  )
)

REM Validasi env vars wajib (sesuai main.py)
if "%TELEGRAM_TOKEN%"=="" (
  echo ERROR: TELEGRAM_TOKEN belum di-set. Isi di .env atau set env var dulu.
  exit /b 1
)
if "%GEMINI_API_KEY%"=="" (
  echo ERROR: GEMINI_API_KEY belum di-set. Isi di .env atau set env var dulu.
  exit /b 1
)
if "%MAPS_API_KEY%"=="" (
  echo ERROR: MAPS_API_KEY belum di-set. Isi di .env atau set env var dulu.
  exit /b 1
)
if "%DEEPSEEK_API_KEY%"=="" (
  echo ERROR: DEEPSEEK_API_KEY belum di-set. Isi di .env atau set env var dulu.
  exit /b 1
)
if "%ALLOWED_CHAT_ID%"=="" (
  echo ERROR: ALLOWED_CHAT_ID belum di-set. Isi di .env atau set env var dulu.
  exit /b 1
)

set "ENV_VARS=TELEGRAM_TOKEN=%TELEGRAM_TOKEN%,GEMINI_API_KEY=%GEMINI_API_KEY%,MAPS_API_KEY=%MAPS_API_KEY%,DEEPSEEK_API_KEY=%DEEPSEEK_API_KEY%,ALLOWED_CHAT_ID=%ALLOWED_CHAT_ID%,GOOGLE_CLOUD_PROJECT=%PROJECT_ID%"
if not "%N8N_WEBHOOK_SECRET%"=="" set "ENV_VARS=%ENV_VARS%,N8N_WEBHOOK_SECRET=%N8N_WEBHOOK_SECRET%"
if not "%GEMINI_MODEL%"==""      set "ENV_VARS=%ENV_VARS%,GEMINI_MODEL=%GEMINI_MODEL%"

gcloud run deploy "%SERVICE_NAME%" ^
  --project "%PROJECT_ID%" ^
  --source . ^
  --region "%REGION%" ^
  --platform managed ^
  --allow-unauthenticated ^
  --set-env-vars "%ENV_VARS%" ^
  --memory 512Mi ^
  --timeout 120 ^
  --service-account god-eye-sa@%PROJECT_ID%.iam.gserviceaccount.com

if errorlevel 1 (
  echo.
  echo Deploy gagal. Lihat error di atas.
  exit /b 1
)

echo.
echo Deploy selesai! Silakan copy URL yang muncul di atas.
echo.
echo Set Telegram webhook:
echo curl "https://api.telegram.org/bot%TELEGRAM_TOKEN%/setWebhook?url=https://SERVICE_URL/webhook"
pause

