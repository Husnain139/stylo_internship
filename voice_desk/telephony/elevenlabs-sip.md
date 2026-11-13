# ElevenLabs SIP mapping (inbound v1)

Use this with the Asterisk bridge in [`bridge/`](bridge/). The PBX never registers to ElevenLabs.

## What v1 does

- **Inbound only:** caller → company DID → Issabel → bridge → ElevenLabs → Stylo order agent.
- **No OpenSIPS** in v1.
- **No AI blind transfer** (`REFER` with `tel:`) in v1. If the caller needs a human, hang up and dial the human queue, or use dialplan fallback when the AI leg fails—not an in-call ElevenLabs transfer.

Add OpenSIPS later only if product requires AI-initiated transfer to a PBX extension.

## ElevenLabs UI steps

1. Open the Stylo agent (`agent_6201m60xdtanewtr7q9r8eda9ebk`) → **Phone numbers** / **SIP trunking**.
2. Import or keep the SIP trunk you already configured (digest username/password or ACL).
3. Assign that number/identity to the **published** Stylo order desk agent.
4. Prefer **TLS** signaling to `sip.rtc.elevenlabs.io:5061` from the bridge.
5. Codecs: ensure **G.711 (PCMU/PCMA)** is allowed (G.722 optional).
6. Do **not** put the Issabel public (or private) IP into ElevenLabs ACL as the only hop—ElevenLabs should see the **bridge** egress IP if ACL is used.

## Bridge side

Templates in [`bridge/config/`](bridge/config/) define:

- `endpoint-pbx` — trusted LAN peer (`PBX_IP`)
- `endpoint-elevenlabs` — outbound TLS trunk (`EL_SIP_USER` / `EL_SIP_PASS`)
- Dialplan: inbound from PBX → dial ElevenLabs destination (`EL_DEST`); on failure → dial `FALLBACK_EXT` back to PBX

Copy values into `bridge/.env`. Never commit secrets.

## Official reference

- ElevenLabs SIP trunking docs: https://elevenlabs.io/docs/eleven-agents/phone-numbers/sip-trunking/

Typical hosts:

| Transport | Host |
|---|---|
| TLS | `sip.rtc.elevenlabs.io:5061` |
| TCP | `sip.rtc.elevenlabs.io:5060` |

## Agent behavior on phone

Same tools and prompt as the widget. Differences:

- No companion product table (web only).
- Caller must still give exactly 7 digits; phone/tracking lookup stays off.
