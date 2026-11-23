# Agent sandboxing (network and files)

Goal: an agent can reach only its model endpoint, and cannot change files outside its workspace. Every other tool
(shell, tests, editors, git) stays available. Code: `src/parbench/sandbox_policy.py`, `src/parbench/landlock.py`,
hooks in `sandbox.py`. Checked 2026-11-23.

## Turning it on

```yaml
# experiment config
sandbox: on            # off (default, behaviour as before) | on (best available, loud fallback) | require
sandbox_allow: []      # extra "host:port" the agent may reach besides the model's base_url
sandbox_writable: []   # extra writable paths in host mode
```

`parbench probe ... --sandbox on` does the same for one probe. On start parbench prints one line per mode, e.g.
`[parbench] SANDBOX MODE: host-landlock | network: TCP connect only to ports [8000] + 32768-60999 | files: workspace only`.
Each `run.json` has `run.sandbox` (`mode`, `network`, `files`, `level`, `allow`), and `runs.csv` has a `sandbox`
column, so runs can be filtered. Runs from before this change have no `sandbox` field.

`require` refuses to start unless network and files are both enforced (`docker-egress`, `host-landlock` with
ABI >= 4 and a local model, `host-seatbelt` with a local model, or `agy-native`).

Only agent containers/workspaces are sandboxed (S0/S1/S2 workers, S4, the S2 merge container where the LLM
resolver runs). Grading containers are unchanged.

## The modes

| Environment | Mode | Network | Files outside the workspace |
|---|---|---|---|
| Docker (Mac, Linux) | `docker-egress` | `--internal` network: no route out, no DNS. The model host name is mapped in `/etc/hosts` to a socat forwarder container (`alpine/socat`, override with `PARBENCH_PROXY_IMAGE`) that forwards only the model port | container filesystem only (as before) |
| Linux host, no root (GPU box) | `host-landlock` | Landlock ABI >= 4: TCP `connect()` only to the model port(s) and the ephemeral range (so tests can start local servers) | Landlock: writes only under the workspace, its private `TMPDIR`, the harness's `XDG_*` dirs, `/dev/{null,zero,full,tty,pts,shm}` |
| macOS host (OpenCode `--host`) | `host-seatbelt` | `sandbox-exec`: outgoing traffic only to loopback (any port) and unix sockets inside the workspace | writes only under the workspace (+ `XDG_*` dirs) |
| neither available | `host-proxyenv` | advisory only: `HTTP(S)_PROXY` points to a dead port | **not enforced** |
| `agy` (Mac host) | `agy-native` | agy's own `--sandbox` (see below) | see below |

All host modes also set `TMPDIR` to `<workspace>/tmp` and the dead proxy variables (with `NO_PROXY` for the model
host), so cooperative tools fail fast.

### Why these choices

- **Docker:** an internal network plus a forwarder needs no iptables, no `NET_ADMIN` and no change to the agent
  image, and the model URL stays the same (`host.docker.internal:<port>`). Forwarding is plain TCP, so it also works
  for an `https://` API host (TLS and SNI pass through). `--network none` would need a socket bridge per harness;
  iptables inside the container needs `NET_ADMIN`, which the agent could then use to undo the rules.
- **Linux host:** Docker is not available on the GPU box and root is not assumed. Landlock is unprivileged, inherited
  by every child, and cannot be lifted. bubblewrap/`unshare` need unprivileged user namespaces, which Ubuntu 24.04
  restricts through AppArmor (`kernel.apparmor_restrict_unprivileged_userns=1`), and `--unshare-net` would also cut
  `localhost` vLLM unless slirp4netns/pasta is added. firejail needs a setuid install. The self-test prints whether
  `unshare -rn` and `bwrap` would have worked, for the record.
- **macOS host:** `sandbox-exec` is deprecated by Apple but works on macOS 26 (and `agy` itself uses it).

## What was tested

| Test | Where | Result |
|---|---|---|
| `docker-egress`: `curl https://example.com` fails (no DNS), `pip download` fails, model `/v1/models` returns 200 through the forwarder, other host ports refused, network and forwarder removed afterwards | Docker Desktop 29.9, Mac arm64 | pass |
| `parbench probe --toy --harness opencode --model qwen3.5-9b-ollama --sandbox on` (a real agent in `docker-egress`) | Docker Desktop, Mac | **not completed**: the Docker Desktop VM became unreachable mid-probe (unrelated `no route to host` to the VM) and did not come back. Re-run this probe before making `on` the default; OpenCode may try to fetch its model catalog or provider package, which is now blocked |
| `scripts/sandbox_selftest.sh` in `host-landlock` (Landlock ABI 8, as root): 11/11 PASS (internet blocked for curl and raw TCP, model port reachable, local test server, workspace writes, `$HOME`, `/tmp` and other dirs blocked, delete outside blocked; signals to PID 1 blocked) | Linux container on Docker Desktop (kernel 7.0) | pass |
| `scripts/sandbox_selftest.sh` in `host-seatbelt`: 11/11 PASS | Mac host | pass |
| Fallback logic (no Landlock -> `host-proxyenv`; ABI 3 -> files only; remote endpoint -> network "NOT enforced"; `require` raises when not fully enforced) | unit check with mocked ABI | pass |
| Ubuntu 24.04 GPU box | **not tested**: run `scripts/sandbox_selftest.sh http://localhost:8000/v1/models` there | UNVERIFIED |
| Docker on plain Linux | **not tested** | UNVERIFIED |

## What is NOT enforced

- **Docker on Linux (UNVERIFIED):** on plain Linux Docker, a container on an internal network may still reach host
  services listening on `0.0.0.0` through the bridge gateway IP. This is the host, not the internet. Not seen on
  Docker Desktop (tested: gateway refused).
- **Landlock (Linux host):**
  - Ports, not hosts: any host on the model port or on an ephemeral port (32768-60999) is reachable over TCP. Web,
    git and package registries (80/443/22) are blocked.
  - UDP is not covered (DNS lookups work; HTTP/3 over UDP 443 would work for a tool that uses it).
  - Pathname unix sockets are not covered. Abstract unix sockets and **signals** are scoped only from ABI 6
    (Linux 6.12); Ubuntu 24.04's GA kernel 6.8 has ABI 4, so there an agent can still `kill` other processes of the
    same user (e.g. a vLLM server started by the same account).
  - Reads are allowed everywhere (an agent can read files outside the workspace, it just cannot send them out over
    the blocked channels).
  - `XDG_*` dirs the harness points outside the workspace stay writable. OpenCode 1.x uses the shared `~/.cache`
    (to keep its npm provider package cached), so `~/.cache` is writable there. That package must already be in the
    cache: with the network blocked OpenCode 1.x cannot download it. Run one unsandboxed probe first.
  - ABI 1 to 3 (Linux 5.13 to 6.6): files only; network is advisory.
- **Seatbelt (Mac host):** reads everywhere; all loopback ports are reachable (other local services); signals are
  not restricted.
- **Remote model endpoints in host mode:** Landlock and seatbelt cannot filter by host, so allowing `api.x.com:443`
  means allowing all of 443; the mode then reports network `NOT enforced`.
- **`host-proxyenv`:** nothing is enforced; an agent can unset the proxy variables.

## `agy` (Antigravity) on the Mac

Tested 2026-11-23 with `agy --sandbox --mode accept-edits` and the `command(*)` allow rule (the adapter's flags):

| Action | Result |
|---|---|
| shell: `curl https://example.com` | blocked (`Could not resolve host`) |
| shell: raw TCP to 1.1.1.1:443 | blocked |
| shell: `curl localhost:11434` | blocked (no loopback either) |
| shell: write in the workspace | allowed |
| shell: write in `$HOME` | blocked (`Operation not permitted`) |
| shell: write in `/tmp` and under `/private/tmp` outside the workspace | **allowed** |
| file tool `write_file` outside the workspace | denied (permission check, headless auto-deny) |

How: `agy` runs each shell command under `sandbox-exec -f ~/.gemini/sandbox/profiles/exebox-*.sb` (deny-default
profile, generated per command and deleted afterwards). The agy process itself (model calls to Google) is not
sandboxed. `run_command` has a `BypassSandbox` parameter that "requests explicit user permission"; whether the
`command(*)` allow rule grants it headless is **UNVERIFIED** (Gemini Flash refused to try it twice).

Decision: **nothing added for agy.** Its shell is already cut off from the network and from `$HOME`; wrapping the
whole agy process in a second profile cannot restrict its network by host (seatbelt only knows `localhost` or `*`)
and would have to allow its writes to `~/.gemini` and the Keychain, so it adds little. The remaining gap is that
shell commands may write to `/tmp` and `$TMPDIR`, which is where the other runs' `parbench-host-*` clones live;
moving host workspaces out of `$TMPDIR` would close it. Not done (it changes where clones live for all host runs).

## Hiding the gold patches and hidden tests (host mode, `hide_gold: true`, the default)

On the host the dataset sits next to the agent. With `hide_gold` (on by default, also with `sandbox: off`) every
host-mode agent command runs under a read guard that denies reads of: the dataset (`feature.patch` = gold,
`tests.patch` = hidden tests), the whole parbench checkout (other runs' `results/`, `.env`, `external/`, and the
main checkout when parbench runs from a git worktree), and the system temp dir that holds every `parbench-host-*`
workspace (other agents' clones and the host grader's clones, which contain `tests.patch`). The agent's own
workspace, parbench's `.venv`, the harness's `XDG_*` dirs and `sandbox_writable` stay readable, and `TMPDIR` points
into the workspace. Host pools (`PARBENCH_HOST_POOLS`) stay readable: they hold only the base repo and the venv.
Each `run.json` records the result in `run.sandbox.gold`.

| Where | How | Tested |
|---|---|---|
| macOS (OpenCode `--host`, host pools) | seatbelt: `(deny file-read* <hidden>)` then `(allow file-read* <workspace>...)` | `tests/test_hide_gold.py` (cat/ls of a hidden dataset dir and another workspace fail; own files, git, python temp files work), and a real OpenCode + qwen3.5:9b probe on the click host pool (see below) |
| Linux (Landlock) | Landlock can only allow, so reads are allowed on every sibling of every ancestor of a hidden path (`landlock.read_allow_list`), plus the workspace | allow-list logic unit-tested; enforcement **UNVERIFIED** (no Linux host here): run `scripts/sandbox_selftest.sh` on the GPU box |
| `agy` | **not possible**: agy's shell already runs under `sandbox-exec`, and sandbox-exec cannot nest (tested: `sandbox_apply: Operation not permitted`); agy's file tools read anywhere | post-hoc only: `parbench audit-leak results/<exp>` |
| Docker | the dataset is not in the container | n/a |

Residual risks: with Landlock, files created later directly in an ancestor dir of a hidden path (e.g. new entries
in `$HOME` when the checkout is under `$HOME`) are unreadable for the agent, which is harmless but surprising;
symlinks the agent creates cannot bypass either mechanism (both check the real path). `agy` runs can read the
gold patches; `audit-leak` flags any tool call that mentions the dataset, `feature.patch`/`tests.patch`, the
checkout path or `results/`, and any network attempt (web tools, and shell `curl`/`wget`/`pip install|download`/
`git clone|fetch|pull`/non-local URLs, which `audit-web` missed). It reads `tool_calls.jsonl`, or the raw logs for
unfinished agents (may over-report).

## Recommendation

- Docker: make `sandbox: on` the default once one real-pool OpenCode run passes with it (the forwarder adds about
  1 to 2 s per container; up to about 30 networks at once fit Docker Desktop's default address pools).
- GPU box: run `scripts/sandbox_selftest.sh` first. If it prints `host-landlock` with 11/11 PASS, use `sandbox: on`
  (or `require`) for the OpenCode runs.
- agy: keep as is; filter by `run.sandbox.mode` if needed.
