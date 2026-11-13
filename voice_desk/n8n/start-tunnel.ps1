# Quick Cloudflare tunnel to local n8n (port 5678).
# Copy the https://*.trycloudflare.com URL into .env as WEBHOOK_URL, then:
#   docker compose up -d
# and update ElevenLabs tool URLs + Publish.

$ErrorActionPreference = "Stop"

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
  Write-Host "cloudflared not found on PATH."
  Write-Host "Install: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/"
  exit 1
}

Write-Host "Starting quick tunnel → http://127.0.0.1:5678"
Write-Host "1) Copy the https://....trycloudflare.com URL from the log below"
Write-Host "2) Set WEBHOOK_URL in voice_desk/n8n/.env to that origin (no /webhook path)"
Write-Host "3) docker compose up -d"
Write-Host "4) Set both ElevenLabs tools to https://<tunnel>/webhook/stylo-order-desk and Publish"
Write-Host ""

cloudflared tunnel --url http://127.0.0.1:5678
