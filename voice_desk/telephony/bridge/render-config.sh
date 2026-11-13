#!/usr/bin/env bash
# Run on the bridge VM from this directory: ./render-config.sh
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "Copy .env.example to .env and fill values first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

LAN_TRANSPORT="${LAN_TRANSPORT:-udp}"
RTP_START="${RTP_START:-10000}"
RTP_END="${RTP_END:-10100}"
EL_SIP_HOST="${EL_SIP_HOST:-sip.rtc.elevenlabs.io}"
EL_SIP_PORT="${EL_SIP_PORT:-5061}"
EL_SIP_TRANSPORT="${EL_SIP_TRANSPORT:-tls}"
AI_DID_PATTERN="${AI_DID_PATTERN:-_X.}"

render() {
  local src="$1"
  local dst="$2"
  sed \
    -e "s|__BRIDGE_IP__|${BRIDGE_IP}|g" \
    -e "s|__PBX_IP__|${PBX_IP}|g" \
    -e "s|__PBX_PORT__|${PBX_PORT}|g" \
    -e "s|__LAN_TRANSPORT__|${LAN_TRANSPORT}|g" \
    -e "s|__AI_DID_PATTERN__|${AI_DID_PATTERN}|g" \
    -e "s|__FALLBACK_EXT__|${FALLBACK_EXT}|g" \
    -e "s|__EL_SIP_USER__|${EL_SIP_USER}|g" \
    -e "s|__EL_SIP_PASS__|${EL_SIP_PASS}|g" \
    -e "s|__EL_SIP_HOST__|${EL_SIP_HOST}|g" \
    -e "s|__EL_SIP_PORT__|${EL_SIP_PORT}|g" \
    -e "s|__EL_SIP_TRANSPORT__|${EL_SIP_TRANSPORT}|g" \
    -e "s|__EL_DEST__|${EL_DEST}|g" \
    -e "s|__RTP_START__|${RTP_START}|g" \
    -e "s|__RTP_END__|${RTP_END}|g" \
    "$src" > "$dst"
}

render config/pjsip.conf.template config/pjsip.conf
render config/extensions.conf.template config/extensions.conf
render config/rtp.conf.template config/rtp.conf

echo "Wrote config/pjsip.conf config/extensions.conf config/rtp.conf"
echo "Next: docker compose up -d"
