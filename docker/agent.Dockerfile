# Agent image = a CooperBench pool image + the agent CLIs. Built per pool by `parbench build-images`.
# Works on Debian/Ubuntu and Alpine bases, amd64 and arm64. Versions match the ones we tested on the Mac.
# Pi needs Node >= 22.19; the script installs Node when missing or too old.
ARG BASE
FROM ${BASE}
ARG HARNESSES="opencode pi claude codex gemini agy"
COPY install_harnesses.sh /tmp/install_harnesses.sh
RUN HARNESSES="${HARNESSES}" sh /tmp/install_harnesses.sh && rm /tmp/install_harnesses.sh
ENV DISABLE_AUTOUPDATER=1 CI=1 GIT_TERMINAL_PROMPT=0
