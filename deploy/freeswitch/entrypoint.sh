#!/bin/sh
# Renders the voip24h gateway + dialplan + Lua bridge script from templates
# (mounted at /templates by the voice-freeswitch-config ConfigMap) into the
# real FreeSWITCH conf tree, using env vars sourced from the
# ai-voice-voip24h-sip Secret + the freeswitch Deployment's env, then execs
# freeswitch. Conf root confirmed by inspecting the built image directly:
# /usr/local/freeswitch/etc/freeswitch (NOT .../conf — that's pre-install-only).
set -e

CONF=/usr/local/freeswitch/etc/freeswitch
VARS='$SIP_EXTENSION $SIP_PASSWORD $SIP_SERVER $VOICE_WS_URL'

mkdir -p "$CONF/scripts"

envsubst "$VARS" < /templates/voip24h-gateway.xml.tpl > "$CONF/sip_profiles/external/voip24h.xml"
cp /templates/00_voip24h_bridge.xml "$CONF/dialplan/public/00_voip24h_bridge.xml"
envsubst "$VARS" < /templates/voip24h_bridge.lua.tpl > "$CONF/scripts/voip24h_bridge.lua"

# mod_audio_fork isn't in the stock autoload list (it's a custom module we
# compiled in); mod_spandsp IS in the stock list but we disabled building it
# (FreeSWITCH v1.10.12's mod_spandsp.c doesn't compile against spandsp 3.1.1's
# v18_init() signature) — both need editing in modules.conf.xml at runtime.
MODULES_XML="$CONF/autoload_configs/modules.conf.xml"
if ! grep -q 'mod_audio_fork' "$MODULES_XML"; then
  sed -i 's#<load module="mod_lua"/>#<load module="mod_lua"/>\n    <load module="mod_audio_fork"/>#' "$MODULES_XML"
fi
sed -i 's#<load module="mod_spandsp"/>#<!--<load module="mod_spandsp"/>-->#' "$MODULES_XML"

exec /usr/local/freeswitch/bin/freeswitch -nonat -nf
