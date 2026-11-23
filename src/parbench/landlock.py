"""Run a command under a Landlock ruleset (Linux >= 5.13, no root needed). Stdlib only.

    python landlock.py [--rw PATH]... [--deny-read PATH]... [--keep-read PATH]... [--connect-port N]...
                       [--connect-range LO-HI]... -- CMD ARGS...
    python landlock.py --check        # print the kernel's Landlock ABI (0 = unavailable) and exit

With --rw, writes (create, delete, rename, truncate, write) are allowed only under the --rw paths. With
--deny-read, the --deny-read paths cannot be read or listed (except --keep-read paths and --rw paths inside them);
everything else stays readable (see read_allow_list). Execution is not restricted. From ABI 4 (Linux 6.7, Ubuntu 24.04's 6.8 has it) outgoing TCP connect() is allowed only to
the listed ports; UDP, unix sockets and ICMP are not covered by Landlock. From ABI 6 the command also cannot send
signals to processes outside the sandbox. The ruleset is inherited by every child and cannot be lifted.
Used by `parbench.sandbox_policy` for host-mode agents.
"""

from __future__ import annotations

import ctypes
import os
import stat
import sys

SYS_CREATE, SYS_ADD_RULE, SYS_RESTRICT = 444, 445, 446  # same numbers on x86_64 and aarch64
CREATE_RULESET_VERSION = 1
RULE_PATH_BENEATH, RULE_NET_PORT = 1, 2
PR_SET_NO_NEW_PRIVS = 38

FS_WRITE_FILE, FS_READ_FILE, FS_READ_DIR = 1 << 1, 1 << 2, 1 << 3
FS_DIR_WRITE = sum(1 << b for b in (4, 5, 6, 7, 8, 9, 10, 11, 12))  # remove dir/file, make char/dir/reg/sock/fifo/block/sym
FS_REFER, FS_TRUNCATE = 1 << 13, 1 << 14  # ABI 2, ABI 3
NET_CONNECT_TCP = 1 << 1  # ABI 4
SCOPE_ABSTRACT_UNIX, SCOPE_SIGNAL = 1 << 0, 1 << 1  # ABI 6


class _RulesetAttr(ctypes.Structure):
    _fields_ = [("fs", ctypes.c_uint64), ("net", ctypes.c_uint64), ("scoped", ctypes.c_uint64)]


class _PathBeneath(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


class _NetPort(ctypes.Structure):
    _fields_ = [("allowed", ctypes.c_uint64), ("port", ctypes.c_uint64)]


def _libc():
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    return libc


def abi() -> int:
    if not sys.platform.startswith("linux"):
        return 0
    r = _libc().syscall(ctypes.c_long(SYS_CREATE), None, ctypes.c_long(0), ctypes.c_long(CREATE_RULESET_VERSION))
    return int(r) if r > 0 else 0


def _under(p: str, d: str) -> bool:
    return p == d or p.startswith(d.rstrip("/") + "/")


def read_allow_list(deny: list[str], keep: list[str]) -> list[str]:
    """Landlock can only allow, so "read everything except `deny`" becomes: allow every sibling of every ancestor
    of a denied path (skipping entries that are, contain or link into a denied path), plus `keep` (re-allowed
    paths inside a denied one). Entries created later directly in an ancestor dir are not readable."""
    deny = [os.path.realpath(d) for d in deny if os.path.exists(d) and os.path.realpath(d) != "/"]
    anc = {os.path.dirname(d) for d in deny}
    for d in list(anc):
        while d != "/":
            d = os.path.dirname(d)
            anc.add(d)
    out = []
    for a in sorted(anc):
        try:
            entries = sorted(os.listdir(a))
        except OSError:
            continue
        for name in entries:
            p = os.path.join(a, name)
            real = os.path.realpath(p)
            if p in anc or any(_under(p, d) or _under(real, d) or _under(d, real) for d in deny):
                continue
            out.append(p)
    return out + [k for k in keep if os.path.exists(k)]


def restrict(rw: list[str], ports: set[int], deny_read: list[str] | None = None,
             keep_read: list[str] | None = None) -> int:
    """Apply the ruleset to the current process. Returns the ABI used. Raises OSError on failure.

    Writes are restricted to `rw` only if `rw` is given; reads are restricted only if `deny_read` is given."""
    libc, v = _libc(), abi()
    if v < 1:
        raise OSError("Landlock is not available (kernel too old, or landlock not in the LSM list)")
    write = (FS_WRITE_FILE | FS_DIR_WRITE | (FS_REFER if v >= 2 else 0) | (FS_TRUNCATE if v >= 3 else 0)) if rw else 0
    read = FS_READ_FILE | FS_READ_DIR if deny_read else 0
    fs = write | read
    net = NET_CONNECT_TCP if v >= 4 and ports else 0
    scoped = (SCOPE_ABSTRACT_UNIX | SCOPE_SIGNAL) if v >= 6 else 0
    attr = _RulesetAttr(fs, net, scoped)
    size = 24 if v >= 6 else 16 if v >= 4 else 8
    fd = libc.syscall(ctypes.c_long(SYS_CREATE), ctypes.byref(attr), ctypes.c_long(size), ctypes.c_long(0))
    if fd < 0:
        raise OSError(ctypes.get_errno(), "landlock_create_ruleset")

    def add(rule_type, rule):
        if libc.syscall(ctypes.c_long(SYS_ADD_RULE), ctypes.c_long(fd), ctypes.c_long(rule_type),
                        ctypes.byref(rule), ctypes.c_long(0)) != 0:
            raise OSError(ctypes.get_errno(), f"landlock_add_rule({rule_type})")

    file_rights = FS_WRITE_FILE | FS_TRUNCATE | FS_READ_FILE  # dir-only rights are EINVAL on files
    rules = [(p, fs) for p in rw] + [(p, read) for p in (read_allow_list(deny_read, keep_read or []) if read else [])]
    for path, rights in rules:
        try:
            pfd = os.open(path, os.O_PATH | os.O_CLOEXEC)
        except OSError:  # vanished or unreachable: nothing to allow
            continue
        try:
            is_dir = stat.S_ISDIR(os.fstat(pfd).st_mode)
            add(RULE_PATH_BENEATH, _PathBeneath(rights if is_dir else rights & file_rights, pfd))
        finally:
            os.close(pfd)
    if net:
        for p in sorted(ports):
            add(RULE_NET_PORT, _NetPort(NET_CONNECT_TCP, p))
    if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "prctl(NO_NEW_PRIVS)")
    if libc.syscall(ctypes.c_long(SYS_RESTRICT), ctypes.c_long(fd), ctypes.c_long(0)) != 0:
        raise OSError(ctypes.get_errno(), "landlock_restrict_self")
    os.close(fd)
    return v


def main(argv: list[str]) -> int:
    if argv[:1] == ["--check"]:
        print(abi())
        return 0
    rw: list[str] = []
    deny: list[str] = []
    keep: list[str] = []
    ports: set[int] = set()
    while argv and argv[0] != "--":
        flag, val, argv = argv[0], argv[1], argv[2:]
        if flag in ("--rw", "--deny-read", "--keep-read"):
            {"--rw": rw, "--deny-read": deny, "--keep-read": keep}[flag].append(val)
        elif flag == "--connect-port":
            ports.add(int(val))
        elif flag == "--connect-range":
            lo, hi = (int(x) for x in val.split("-"))
            ports.update(range(lo, hi + 1))
        else:
            raise SystemExit(f"landlock.py: unknown flag {flag}")
    cmd = argv[1:]
    if not cmd:
        raise SystemExit("landlock.py: no command after --")
    try:
        restrict(rw, ports, deny, keep + rw)
    except OSError as e:  # never run the command unconfined when confinement was asked for
        print(f"landlock.py: cannot apply sandbox: {e}", file=sys.stderr)
        return 126
    os.execvp(cmd[0], cmd)
    return 127


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
