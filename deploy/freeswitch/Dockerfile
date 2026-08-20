# syntax=docker/dockerfile:1
# FreeSWITCH built from source + mod_audio_fork (bidirectional WS audio
# bridge) for the voip24h SIP trunk integration. Built from source — not
# from a prebuilt image — because mod_audio_fork needs FreeSWITCH dev
# headers that exactly match the running libfreeswitch.so, and no public
# prebuilt FreeSWITCH image ships both the binary and matching headers.
#
# See docs on the voip24h integration: voip24h's /v3/call/dial API rings
# an extension first and only bridges to the outbound phone number once
# that extension answers — there is no WebSocket/RTP hand-off for a
# third party. FreeSWITCH plays that extension (registers as a real SIP
# UA with voip24h), auto-answers, and mod_audio_fork forks the bridged
# call's PCM audio out to the voice worker over WebSocket, and plays
# audio the voice worker sends back — the same shape as CloudFone's own
# WS protocol, just at the SIP/RTP layer instead of a native web socket.
FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    git cmake build-essential pkg-config automake autoconf libtool \
    libssl-dev libcurl4-openssl-dev libpcre3-dev libspeexdsp-dev \
    libedit-dev libsqlite3-dev libopus-dev libsndfile1-dev \
    libwebsockets-dev libboost-dev uuid-dev libtool-bin \
    libpq-dev libavformat-dev libavcodec-dev libavutil-dev libswscale-dev \
    zlib1g-dev libjpeg62-turbo-dev liblua5.3-dev \
    unixodbc-dev libpcap-dev libldns-dev libmemcached-dev libyaml-dev \
    python3-dev libgdbm-dev libshout3-dev libmpg123-dev libmp3lame-dev \
    libflac-dev libogg-dev libvorbis-dev libsamplerate0-dev libtiff-dev \
    ca-certificates wget yasm nasm \
    && rm -rf /var/lib/apt/lists/*

# Debian bookworm's libspandsp-dev is spandsp 2.x; FreeSWITCH v1.10 requires
# spandsp3 (not packaged for bookworm) — build FreeSWITCH's own fork from
# source first so ./configure's spandsp >= 3.0 check succeeds.
WORKDIR /src
RUN git clone --depth 1 -b v3.1.1 https://github.com/freeswitch/spandsp.git spandsp
WORKDIR /src/spandsp
RUN ./bootstrap.sh \
 && ./configure \
 && make -j"$(nproc)" \
 && make install \
 && ldconfig

# Same story as spandsp: bookworm has no sofia-sip-ua package new enough
# (FreeSWITCH needs >= 1.13.17) — build FreeSWITCH's fork from source.
WORKDIR /src
RUN git clone --depth 1 -b v1.13.18 https://github.com/freeswitch/sofia-sip.git sofia-sip
WORKDIR /src/sofia-sip
RUN ./bootstrap.sh \
 && ./configure \
 && make -j"$(nproc)" \
 && make install \
 && ldconfig

WORKDIR /src
RUN git clone --depth 1 -b v1.10.12 https://github.com/signalwire/freeswitch.git freeswitch

WORKDIR /src/freeswitch
# mod_verto/mod_rtc/mod_signalwire need SignalWire's own libks (WebRTC
# signaling), which isn't packaged for bookworm and isn't needed here — we
# only need SIP (mod_sofia) + Lua + mod_audio_fork. Disable them instead of
# building yet another from-source dependency chain.
RUN ./bootstrap.sh -j \
 && sed -i \
      -e 's/^\(endpoints\/mod_verto\)/#\1/' \
      -e 's/^\(endpoints\/mod_rtc\)/#\1/' \
      -e 's/^\(applications\/mod_signalwire\)/#\1/' \
      -e 's/^\(applications\/mod_spandsp\)/#\1/' \
      modules.conf \
 && ./configure --prefix=/usr/local/freeswitch \
 && make -j"$(nproc)" \
 && make install

WORKDIR /src
RUN git clone --depth 1 https://github.com/byteroycai/mod_audio_fork.git mod_audio_fork
WORKDIR /src/mod_audio_fork
RUN cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
      -DFREESWITCH_INCLUDE_DIR=/usr/local/freeswitch/include/freeswitch \
      -DFREESWITCH_LIBRARY=/usr/local/freeswitch/lib/libfreeswitch.so \
 && cmake --build build --parallel \
 && cp build/mod_audio_fork.so /usr/local/freeswitch/lib/freeswitch/mod/

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 libcurl4 libpcre3 libspeexdsp1 libedit2 libsqlite3-0 \
    libopus0 libsndfile1 libwebsockets17 uuid-runtime ca-certificates \
    libpq5 libavformat59 libavcodec59 libavutil57 libswscale6 \
    gettext-base unixodbc liblua5.3-0 libldns3 libmemcached11 \
    libyaml-0-2 libgdbm6 libmpg123-0 libmp3lame0 libflac12 libogg0 \
    libvorbis0a libvorbisenc2 libsamplerate0 libtiff6 libpcap0.8 \
    libshout3 python3 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/freeswitch /usr/local/freeswitch
# spandsp3 was built from source into /usr/local/lib (not an apt package on
# bookworm) — copy its runtime libs across too, then refresh the loader cache.
COPY --from=builder /usr/local/lib /usr/local/lib
RUN ldconfig
ENV PATH="/usr/local/freeswitch/bin:${PATH}"
COPY entrypoint.sh /entrypoint.sh
COPY templates/ /templates/
RUN chmod +x /entrypoint.sh
EXPOSE 5060/udp
EXPOSE 16384-16884/udp
ENTRYPOINT ["/entrypoint.sh"]
