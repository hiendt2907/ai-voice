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

-- Real argv syntax (verified against mod_audio_fork.c, README's shorthand
-- omits this): <uuid> start <url> <mix> <rate> <bugname> <metadata>
-- <bidir_enable> <bidir_stream> <bidir_rate>. bidir_enable=true is required
-- (confirmed live: without it every playAudio JSON is dropped with
-- "bidirectional audio is disabled"). bidir_stream must match the
-- adapter's audio_mode query param on ws_url (telephony/freeswitch.py):
-- "json" sends playAudio JSON (bidir_stream=false expected by the module),
-- "stream" sends raw binary frames (bidir_stream=true expected). Both drain
-- into the same playoutBuffer/dub_speech_frame mechanism on the FreeSWITCH
-- side though, which is the thing suspected broken —
-- see https://github.com/byteroycai/mod_audio_fork/issues/1.
local bidir_stream = "${AUDIO_MODE}" == "stream" and "true" or "false"
local api = freeswitch.API()
local cmd = string.format(
  "%s start %s mono 8k audio_fork %s true %s 8000",
  uuid, ws_url, metadata, bidir_stream
)
local result = api:executeString("uuid_audio_fork " .. cmd)
freeswitch.consoleLog("INFO", "[voip24h_bridge] uuid_audio_fork start -> " .. tostring(result) .. "\n")

session:setAutoHangup(false)
while session:ready() do
  session:sleep(500)
end

freeswitch.consoleLog("INFO", "[voip24h_bridge] session ended for " .. uuid .. "\n")
