#!/usr/bin/env bash
# Log Antigravity account N into its own agy profile, once, interactively (see configs/agy_accounts.yaml).
#   scripts/agy_login_account.sh 2
# The profile is a separate HOME with its own keychain (empty password, never in your keychain search list),
# so this does not touch your normal agy login (account 1 = "~"). In the agy window: sign in with the Google
# account you want as account N, then quit (/quit or Ctrl-C twice). The script then checks with `agy models`.
set -euo pipefail
N=${1:?usage: $0 N   (N >= 2; account 1 is your normal login)}
cd "$(dirname "$0")/.."
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
P=$(PYTHONPATH=src "$PY" -c "import sys; from parbench.agy_accounts import profiles; print(profiles()[int(sys.argv[1]) - 1])" "$N")
if [ "$(cd ~ && pwd -P)" = "$(mkdir -p "$P" && cd "$P" && pwd -P)" ]; then
  echo "account $N is your normal HOME; log in with plain 'agy'"; exit 1
fi
KC="$P/Library/Keychains/login.keychain-db"
mkdir -p "$P/Library/Keychains"
if [ ! -f "$KC" ]; then
  HOME="$P" security create-keychain -p "" "$KC"
  HOME="$P" security set-keychain-settings "$KC"   # no auto-lock
fi
HOME="$P" security unlock-keychain -p "" "$KC"
echo "profile for account $N: $P"
echo "Sign in with the account you want as account $N, then quit agy."
(cd "$P" && HOME="$P" agy)
echo "check:"
(cd "$P" && HOME="$P" agy models | head -5)
