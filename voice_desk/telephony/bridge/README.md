# Asterisk Docker bridge

Inbound-only SIP gateway: **Issabel/Elastix (LAN)** ↔ **this host** ↔ **ElevenLabs (TLS out)**.

## Deploy on the bridge VM

1. Copy this `bridge/` folder to the Linux VM.
2. `cp .env.example .env` and fill IT values (see [`../README.md`](../README.md)).
3. `chmod +x render-config.sh && ./render-config.sh`
4. `docker compose up -d`
5. `docker logs -f stylo-sip-bridge`

Asterisk must see rendered files `config/pjsip.conf`, `config/extensions.conf`, `config/rtp.conf` (generated; gitignore them if they contain secrets).

## Issabel / Elastix

- Add a SIP trunk/peer to `BRIDGE_IP` (same LAN transport/port as `.env`).
- Route the AI DID (or IVR option) to that trunk.
- Do **not** add an ElevenLabs trunk on the PBX.

## Image note

The compose file uses `andrius/asterisk:latest` as a starting point. If your image layout differs, mount the same conf files to that image’s Asterisk config path and keep `network_mode: host` so RTP works.

## Fallback

If `Dial` to ElevenLabs fails, dialplan sends the caller to `FALLBACK_EXT` on the PBX peer.

## Security

- Allow SIP/RTP from `PBX_IP` only on the LAN.
- Allow outbound from the bridge to `sip.rtc.elevenlabs.io` only.
- Never commit `.env` or rendered conf with passwords.
