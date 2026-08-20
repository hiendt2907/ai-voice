-- Bridges this leg's audio to the voice worker over WebSocket via
-- mod_audio_fork (bidirectional: caller PCM out, TTS PCM back in).
-- Rendered from this .tpl by entrypoint.sh (envsubst) at container start.

local uuid = session:get_uuid()
local caller_number = session:getVariable("caller_id_number") or ""
local ws_url = "${VOICE_WS_URL}"

local metadata = string.format(
  '{"callId":"%s","callerIdNumber":"%s","direction":"outbound","provider":"voip24h"}',
  uuid, caller_number
)

local api = freeswitch.API()
local cmd = string.format("%s start %s mono 8k %s", uuid, ws_url, metadata)
local result = api:executeString("uuid_audio_fork " .. cmd)
freeswitch.consoleLog("INFO", "[voip24h_bridge] uuid_audio_fork start -> " .. tostring(result) .. "\n")

session:setAutoHangup(false)
while session:ready() do
  session:sleep(500)
end

freeswitch.consoleLog("INFO", "[voip24h_bridge] session ended for " .. uuid .. "\n")
