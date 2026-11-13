# Bridge test checklist

Do these in order. Fill IT fields from [`README.md`](README.md) first.

## 1. Bridge host

- [ ] Bridge VM has static `BRIDGE_IP`
- [ ] Docker installed; `bridge/.env` filled from `.env.example` (not committed)
- [ ] `docker compose up -d` in `bridge/` succeeds
- [ ] `docker compose logs -f` shows Asterisk running, no crash loop
- [ ] From bridge: `ping` / DNS resolves `sip.rtc.elevenlabs.io`

## 2. LAN peer (PBX → bridge)

- [ ] Issabel/Elastix peer points at `BRIDGE_IP` with matching transport/port
- [ ] Bridge ACL allows only `PBX_IP`
- [ ] Test call from PBX to a bridge echo/test extension (if configured) or watch Asterisk CLI: `pjsip set logger on` and confirm INVITE arrives
- [ ] No route from PBX to the public internet for this call path

## 3. Cloud peer (bridge → ElevenLabs)

- [ ] Firewall allows bridge → `sip.rtc.elevenlabs.io` TCP/TLS 5060/5061 and RTP range
- [ ] ElevenLabs SIP trunk credentials match `.env`
- [ ] Stylo order agent is assigned to the SIP number/identity in ElevenLabs
- [ ] Agent published; Mock tools Off
- [ ] Outbound test from bridge reaches ElevenLabs (INVITE 200 / early media / agent greeting)

## 4. Full inbound path

- [ ] External (or simulated) call to company DID
- [ ] Call lands on Issabel → bridge → ElevenLabs agent greeting
- [ ] Say 7 digits of a known order → status speak works (n8n execution green)
- [ ] Cancel request logs to the sheet; agent says order was not changed
- [ ] Hang up cleanly (BYE both legs)

## 5. Fallback

- [ ] Stop bridge or block ElevenLabs briefly
- [ ] Inbound call returns to `FALLBACK_EXT` human queue on the PBX
- [ ] Restore bridge; AI path works again

## 6. Non-phone control

- [ ] Widget demo still works at http://127.0.0.1:8765 (product panel is web-only)
