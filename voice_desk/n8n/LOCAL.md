# Local n8n demo (PC + Cloudflare Tunnel)

Run the Stylo order desk without n8n Cloud. Docker n8n on your PC; Cloudflare quick tunnel gives ElevenLabs a public HTTPS URL.

## Limits

- PC + Docker must stay on during demos.
- Quick tunnel URL **changes** every time you restart `cloudflared` (unless you later use a named tunnel).
- After each new tunnel URL: update `.env` `WEBHOOK_URL`, restart n8n, update ElevenLabs tool URLs, publish.

## 0. Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) running
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/) on PATH (`cloudflared --version`)
- Workflow export: [`Stylo-order-desk.json`](Stylo-order-desk.json) (or your cloud export)
- Desk secrets go in **`voice_desk/n8n/.env`** (not paid n8n UI Variables). Code nodes already read `$env`.

## 1. Start n8n

```powershell
cd C:\Users\hp\stylo_internship\voice_desk\n8n
copy .env.example .env
# Edit .env: DESK_SECRET, GINKGO_BASE_URL, GINKGO_AUTH, SHEET_ID
docker compose up -d
```

Open **http://127.0.0.1:5678** (prefer `127.0.0.1` over `localhost` if login cookies fail) and create the owner account (first visit only).

If login breaks later:

```powershell
docker exec stylo-n8n n8n user-management:reset
```

Then open the UI again and create a new owner.

License key email (workflow history / folders) is **optional** for this desk. You do **not** need paid Variables.

## 2. Import workflow

1. **Workflows → Import from file** → `Stylo-order-desk.json`
2. Confirm Webhook path is `stylo-order-desk` (POST)
3. Open **Append request** → reconnect Google Sheets credential (cloud OAuth does not carry over). Sheet id comes from `$env.SHEET_ID` in `.env`.
4. **Save** → **Active**

Optional: if Code nodes are stale, paste from `normalize-request.js`, `speak-from-ginkgo.js`, `resolve-log.js`.

After changing `.env` secrets:

```powershell
docker compose up -d
```

## 3. Public tunnel

In a **second** terminal:

```powershell
cd C:\Users\hp\stylo_internship\voice_desk\n8n
.\start-tunnel.ps1
```

Or:

```powershell
cloudflared tunnel --url http://127.0.0.1:5678
```

Copy the `https://….trycloudflare.com` URL (origin only, no path).

## 4. Point n8n at the tunnel

Edit `voice_desk/n8n/.env`:

```env
N8N_WEBHOOK_URL=https://YOUR_SUBDOMAIN.trycloudflare.com/
WEBHOOK_URL=https://YOUR_SUBDOMAIN.trycloudflare.com/
```

Trailing slash optional; n8n normalizes it. Then:

```powershell
docker compose up -d
```

In the workflow, open the Webhook node and confirm the **Production** URL looks like:

`https://YOUR_SUBDOMAIN.trycloudflare.com/webhook/stylo-order-desk`

## 5. Point ElevenLabs at the tunnel

1. Both tools `lookup_order` and `log_request`:
   - URL = `https://YOUR_SUBDOMAIN.trycloudflare.com/webhook/stylo-order-desk`
   - Header `X-Desk-Secret` = same as n8n `DESK_SECRET`
2. **Publish** the agent

Template: [`../agent/tools.json`](../agent/tools.json) (replace `YOUR_TUNNEL_URL`).

## 6. Smoke test

1. Demo page: `cd ..\demo` → `python -m http.server 8765` → http://127.0.0.1:8765  
2. Say 7 digits → n8n **Executions** shows success; agent speaks status  
3. Cancel → sheet row; “order was not changed”  
4. If 401: secret mismatch. If timeout: tunnel/n8n down or wrong `WEBHOOK_URL`

## Quick restart (next demo day)

```powershell
cd C:\Users\hp\stylo_internship\voice_desk\n8n
docker compose up -d
.\start-tunnel.ps1
# paste new URL into .env WEBHOOK_URL → docker compose up -d
# update ElevenLabs tool URLs → Publish
```
