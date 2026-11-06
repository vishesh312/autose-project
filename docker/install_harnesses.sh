#!/bin/sh
# Install agent CLIs into a pool image. Sources: docs/harnesses.md. Each harness failure is non-fatal
# (reported at the end) so one broken download does not block the others.
set -u
OPENCODE_V=2.2.4; PI_V=0.84.4; CLAUDE_V=2.1.319; CODEX_V=0.166.0; GEMINI_V=0.34.0
FAILED=""

# --- base packages (bash, curl, git, ripgrep, timeout) ---
if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq && apt-get install -y -qq --no-install-recommends bash curl ca-certificates git ripgrep fd-find xz-utils >/dev/null
  rm -rf /var/lib/apt/lists/*
  LIBC=glibc
elif command -v apk >/dev/null 2>&1; then
  apk add --no-cache bash curl ca-certificates git ripgrep fd libgcc libstdc++ xz coreutils >/dev/null
  LIBC=musl
else
  echo "unsupported base image (no apt-get/apk)"; exit 1
fi
case "$(uname -m)" in x86_64|amd64) ARCH=x64; CARCH=x86_64;; aarch64|arm64) ARCH=arm64; CARCH=aarch64;; esac
SUF=""; [ "$LIBC" = musl ] && SUF="-musl"

# --- Node >= 22.19 (needed by pi, gemini; also used for npm fallbacks) ---
need_node() { command -v node >/dev/null 2>&1 || return 0
  node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>22||(a==22&&b>=19)?0:1)'; }
if need_node; then
  if [ "$LIBC" = musl ]; then
    apk add --no-cache nodejs npm >/dev/null || FAILED="$FAILED node"
  else
    f=$(curl -fsSL https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt | grep -o "node-v[0-9.]*-linux-$ARCH.tar.xz" | head -1)
    curl -fsSL "https://nodejs.org/dist/latest-v22.x/$f" | tar -xJ -C /usr/local --strip-components=1 || FAILED="$FAILED node"
  fi
fi

has() { echo " $HARNESSES " | grep -q " $1 "; }
npm_i() { npm i -g --ignore-scripts "$@" >/dev/null 2>&1; }

has claude && { curl -fsSL -o /usr/local/bin/claude \
    "https://downloads.claude.ai/claude-code-releases/$CLAUDE_V/linux-$ARCH$SUF/claude" \
    && chmod +x /usr/local/bin/claude || FAILED="$FAILED claude"; }
has codex && { curl -fsSL "https://github.com/openai/codex/releases/download/rust-v$CODEX_V/codex-$CARCH-unknown-linux-musl.tar.gz" \
    | tar -xz -C /usr/local/bin && mv /usr/local/bin/codex-* /usr/local/bin/codex 2>/dev/null; \
    command -v codex >/dev/null || npm_i @openai/codex@$CODEX_V || FAILED="$FAILED codex"; }
has opencode && { d=$(mktemp -d) && curl -fsSL "https://registry.npmjs.org/@opencode/cli-linux-$ARCH$SUF/-/cli-linux-$ARCH$SUF-$OPENCODE_V.tgz" \
    | tar -xz -C "$d" && install -m755 "$d/package/bin/opencode" /usr/local/bin/opencode \
    || npm_i @opencode/cli@$OPENCODE_V || FAILED="$FAILED opencode"; }
has pi && { npm_i @earendil-works/pi-coding-agent@$PI_V || FAILED="$FAILED pi"; }
has gemini && { npm_i @google/gemini-cli@$GEMINI_V || FAILED="$FAILED gemini"; }
has agy && { curl -fsSL https://antigravity.google/cli/install.sh | bash -s -- --dir /usr/local/bin >/dev/null 2>&1 \
    || FAILED="$FAILED agy"; }

# git identity for agents that commit; allow any owner
git config --system user.email parbench@local; git config --system user.name parbench
git config --system --add safe.directory '*'

echo "installed:"; for b in claude codex opencode pi gemini agy; do command -v $b >/dev/null 2>&1 && echo "  $b"; done
[ -n "$FAILED" ] && echo "FAILED:$FAILED"
exit 0
