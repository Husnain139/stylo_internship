# Company SIP bridge (inbound only)

Issabel/Elastix stays on the LAN. A small **bridge VM** is the only host that talks to ElevenLabs over outbound SIP TLS. The Stylo order agent and n8n tools do not change.

```text
Caller → company DID → Issabel/Elastix
                         → SIP (LAN only) → Bridge VM (Asterisk)
                                              → SIP TLS → ElevenLabs
                                                              → Stylo agent → n8n / Ginkgo
```

## Why a bridge

- The PBX must not be exposed on the public internet.
- Direct PBX ↔ ElevenLabs is refused by company policy.
- The bridge is IP-allowlisted on the LAN and is the only machine allowed outbound to `sip.rtc.elevenlabs.io`.

## Compliance note

This topology solves **exposure**. It does **not** keep voice media inside Pakistan. RTP still leaves through the bridge to ElevenLabs. IT and legal must approve that egress. This folder is not PTA or legal advice.

## What stays the same

- Agent, tools, n8n, Ginkgo lookup, sheet logging.
- Web demo product panel is **browser only**. Phone callers hear voice only.

## Minimum IT fields

Fill these before cutover (no full PBX diagram required):

| Field | Example | Notes |
|---|---|---|
| `BRIDGE_IP` | `192.168.1.50` | Static LAN IP of the bridge VM |
| `PBX_IP` | `192.168.1.10` | Issabel/Elastix signaling IP |
| `PBX_PORT` | `5060` | LAN SIP port |
| `LAN_TRANSPORT` | `udp` | `udp` or `tcp` between PBX and bridge |
| `AI_DID_PATTERN` | `042xxxxxxx` or `_X.` | Inbound pattern sent to the bridge |
| `FALLBACK_EXT` | `1000` | Human queue if ElevenLabs is down |
| `EL_SIP_USER` / `EL_SIP_PASS` | (from ElevenLabs UI) | Digest auth for the cloud leg |
| `EL_DEST` | phone or trunk identity | Destination assigned to the Stylo agent in ElevenLabs |
| Firewall | bridge → `sip.rtc.elevenlabs.io:5060/5061` + RTP | Outbound only from the bridge |

Copy [`bridge/.env.example`](bridge/.env.example) to `bridge/.env` on the VM. **Do not commit real passwords.**

## Cutover (high level)

1. Deploy the Docker Asterisk bridge on a LAN VM ([`bridge/`](bridge/)).
2. In Issabel/Elastix, add a SIP trunk/peer to `BRIDGE_IP` and route the AI DID there.
3. In ElevenLabs, keep or create the SIP trunk; assign the Stylo order agent; use digest or ACL as configured.
4. Open outbound firewall from the bridge only.
5. Run [`checklist.md`](checklist.md).

Detail for ElevenLabs: [`elevenlabs-sip.md`](elevenlabs-sip.md).

## Out of scope (v1)

- Outbound AI dialer
- AI blind transfer to humans via `REFER` (needs OpenSIPS later)
- Exposing Issabel publicly
- Changing order-desk prompts for telephony
