"""Token meter: a small reverse proxy in front of an OpenAI-compatible endpoint (stdlib only).

parbench starts one Meter per run on the host and points the harness at it, so every model request (main
session, subagent child sessions, title generation, compaction, retries) is counted from the server's own
`usage`, independent of what the harness chooses to report. See docs/metrics_tokens.md.

  harness --> http://<host>:<port>/m/<tag>/v1/... --> upstream (e.g. http://localhost:8000/v1/...)

`<tag>` names the agent; the meter strips `/m/<tag>` and forwards the rest unchanged. Requests are NOT
modified (body and headers pass through; only Host and hop-by-hop headers are replaced). Usage is read from
the JSON response `usage` or, for SSE streams, the last chunk that carries `usage`. If a stream has no usage
chunk (the client did not ask for `stream_options.include_usage` and the server does not force it; vLLM:
`--enable-force-include-usage`), the request is logged with `usage_missing: true` and counted, never guessed.
"""

from __future__ import annotations

import gzip
import http.client
import json
import os
import threading
import time
import zlib
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .config import Usage

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
       "transfer-encoding", "upgrade", "host", "content-length"}
_ACTIVE: dict[str, "Meter"] = {}  # meter base URL (as given to harnesses) -> Meter


def usage_from_body(body: bytes, encoding: str | None = None) -> dict | None:
    """The `usage` object of a JSON response or of an SSE stream (last chunk with usage), else None."""
    if encoding in ("gzip", "deflate"):
        try:
            body = gzip.decompress(body) if encoding == "gzip" else zlib.decompress(body)
        except Exception:
            return None
    text = body.decode("utf-8", "replace")
    found = None
    if text.lstrip().startswith("{"):
        try:
            obj = json.loads(text)
            found = obj.get("usage") or _ollama_native(obj)
        except Exception:
            pass
        return found
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("usage"):
            found = obj["usage"]
    return found


def _ollama_native(obj: dict) -> dict | None:  # /api/chat, /api/generate
    if "prompt_eval_count" in obj or "eval_count" in obj:
        return {"prompt_tokens": obj.get("prompt_eval_count", 0), "completion_tokens": obj.get("eval_count", 0)}
    return None


def normalise(u: dict) -> dict:
    """OpenAI usage -> prompt (all input incl. cached), cached, completion (incl. reasoning), reasoning."""
    ptd = u.get("prompt_tokens_details") or {}
    ctd = u.get("completion_tokens_details") or {}
    return {"prompt_tokens": u.get("prompt_tokens", u.get("input_tokens", 0)) or 0,
            "cached_tokens": ptd.get("cached_tokens", 0) or 0,
            "completion_tokens": u.get("completion_tokens", u.get("output_tokens", 0)) or 0,
            "reasoning_tokens": ctd.get("reasoning_tokens", 0) or 0}


class Meter:
    def __init__(self, upstream: str, bind: str = "127.0.0.1", public_host: str = "localhost"):
        u = urlparse(upstream)
        self.upstream_scheme, self.upstream_netloc = u.scheme, u.netloc
        self.upstream_path = u.path.rstrip("/")
        self.public_host = public_host
        self.lock = threading.Lock()
        self.records: dict[str, list[dict]] = {}
        self.logs: dict[str, Path] = {}
        meter = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"  # one request per connection; body ends at close (simple, streams fine)

            def log_message(self, *a):
                pass

            def _any(self):
                meter._handle(self)

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _any

        self.server = ThreadingHTTPServer((bind, 0), H)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.base_url = f"http://{public_host}:{self.port}/m/_{self.upstream_path}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        _ACTIVE[self.base_url] = self

    # ------------------------------------------------------------- agent view
    def url_for(self, tag: str) -> str:
        return f"http://{self.public_host}:{self.port}/m/{tag}{self.upstream_path}"

    def attach(self, tag: str, log_path: Path | None) -> None:
        with self.lock:
            self.records.setdefault(tag, [])
            if log_path:
                self.logs[tag] = log_path

    def usage_of(self, tag: str, start: int = 0) -> tuple[Usage, int]:
        """Usage of this agent's requests from index `start` on, and the new request count."""
        with self.lock:
            recs = list(self.records.get(tag, []))
        return _sum(recs[start:]), len(recs)

    def summary(self, tag: str) -> dict:
        with self.lock:
            recs = list(self.records.get(tag, []))
        return {"usage": _sum(recs).to_json(), "requests": len(recs),
                "requests_failed": sum(1 for r in recs if r["status"] >= 400 or r.get("error")),
                "requests_usage_missing": sum(1 for r in recs if r.get("usage_missing")),
                "by_kind": _count(r["kind"] for r in recs)}

    def close(self) -> None:
        _ACTIVE.pop(self.base_url, None)
        self.server.shutdown()
        self.server.server_close()

    # ------------------------------------------------------------- proxying
    def _handle(self, h: BaseHTTPRequestHandler) -> None:
        t0 = time.time()
        path = h.path
        tag = "_"
        if path.startswith("/m/"):
            tag, _, rest = path[3:].partition("/")
            path = "/" + rest
        n = int(h.headers.get("Content-Length") or 0)
        body = h.rfile.read(n) if n else b""
        rec = {"ts": t0, "method": h.command, "path": path, "status": 0, **_describe_request(path, body)}
        headers = {k: v for k, v in h.headers.items() if k.lower() not in HOP}
        headers["Host"] = self.upstream_netloc
        if body:
            headers["Content-Length"] = str(len(body))
        conn_cls = http.client.HTTPSConnection if self.upstream_scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(self.upstream_netloc, timeout=3600)
        buf = bytearray()
        try:
            conn.request(h.command, path, body=body or None, headers=headers)
            resp = conn.getresponse()
            rec["status"] = resp.status
            h.send_response_only(resp.status, resp.reason)
            for k, v in resp.getheaders():
                if k.lower() not in HOP:
                    h.send_header(k, v)
            h.send_header("Connection", "close")
            h.end_headers()
            first = True
            client_ok = True
            while True:
                chunk = resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536)
                if not chunk:
                    break
                if first:
                    rec["ttfb_s"] = round(time.time() - t0, 3)
                    first = False
                buf += chunk
                if client_ok:
                    try:
                        h.wfile.write(chunk)
                        h.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        client_ok = False  # keep reading so the usage of the finished generation is still logged
                        rec["client_disconnected"] = True
            usage = usage_from_body(bytes(buf), resp.getheader("Content-Encoding"))
        except Exception as e:  # upstream unreachable or broken mid-response
            rec["error"] = f"{type(e).__name__}: {e}"[:300]
            usage = usage_from_body(bytes(buf)) if buf else None
            if not rec["status"]:
                try:
                    h.send_error(502, "meter: upstream error")
                except Exception:
                    pass
        finally:
            conn.close()
        rec["latency_s"] = round(time.time() - t0, 3)
        if usage:
            rec.update(normalise(usage))
        else:
            rec.update(prompt_tokens=None, cached_tokens=None, completion_tokens=None, reasoning_tokens=None)
            rec["usage_missing"] = rec["kind"] in ("chat", "completion", "responses") and rec["status"] == 200
        with self.lock:
            self.records.setdefault(tag, []).append(rec)
            log = self.logs.get(tag)
            if log:
                with open(log, "a") as f:
                    f.write(json.dumps(rec) + "\n")


def _describe_request(path: str, body: bytes) -> dict:
    kind = ("chat" if path.endswith("/chat/completions") else "completion" if path.endswith("/completions")
            else "responses" if path.endswith("/responses") else "models" if path.endswith("/models") else "other")
    d: dict = {"kind": kind}
    if body and kind in ("chat", "completion", "responses"):
        try:
            req = json.loads(body)
            d.update(model=req.get("model"), stream=bool(req.get("stream")),
                     include_usage=bool((req.get("stream_options") or {}).get("include_usage")),
                     n_messages=len(req.get("messages") or req.get("input") or []),
                     n_tools=len(req.get("tools") or []), max_tokens=req.get("max_tokens") or req.get("max_completion_tokens"))
        except Exception:
            pass
    return d


def _sum(recs: list[dict]) -> Usage:
    u = Usage()
    for r in recs:
        if r.get("prompt_tokens") is not None:
            u = u + Usage(input=r["prompt_tokens"], cached_input=r["cached_tokens"], output=r["completion_tokens"],
                          reasoning=r["reasoning_tokens"], calls=1)
    return u


def _count(it) -> dict:
    out: dict = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return out


# ----------------------------------------------------------------- integration
def start_for(model, host_mode: bool):
    """Start a meter for this run's model if it has an OpenAI-compatible base_url; return (meter, model')
    where model'.base_url points at the meter. Off with PARBENCH_METER=0."""
    if os.environ.get("PARBENCH_METER", "1") == "0" or model.provider != "openai_compat" or not model.base_url:
        return None, model
    upstream = model.base_url.replace("host.docker.internal", "localhost")  # the meter runs on the host
    # Containers reach the host as host.docker.internal; on Linux that is the bridge IP, so listen on all
    # interfaces then (override with PARBENCH_METER_BIND). Host-mode agents use loopback.
    bind = os.environ.get("PARBENCH_METER_BIND") or ("127.0.0.1" if host_mode else "0.0.0.0")
    m = Meter(upstream, bind=bind, public_host="localhost" if host_mode else "host.docker.internal")
    return m, replace(model, base_url=m.base_url)


def for_agent(model, tag: str, log_path: Path | None):
    """If `model` points at an active meter, return (meter, model with a per-agent URL); else (None, model)."""
    m = _ACTIVE.get(model.base_url or "")
    if not m:
        return None, model
    m.attach(tag, log_path)
    return m, replace(model, base_url=m.url_for(tag))
