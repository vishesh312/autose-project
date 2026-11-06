#!/usr/bin/env python3
"""Smoke-test an LLM server before pointing coding agents at it.

Dependency-free (stdlib only). Checks:
  models     GET  {base}/models lists the model                       (WARN only)
  chat       POST {base}/chat/completions returns text
  tool_call  model emits a well-formed `read_file` tool call (parsed by the
             server into `tool_calls`, not left as raw markup in `content`)
  tool_rt    tool result is sent back and the model answers (round-trip)
  anthropic  POST {root}/v1/messages, text + tool_use        (--anthropic)
  responses  POST {base}/responses, text + function_call     (--responses)
  parallel   N concurrent streamed requests: latency, TTFT, tok/s (--parallel N)

Usage:
  python scripts/check_endpoint.py --base-url http://localhost:11434/v1 --model qwen3.5:9b
  python scripts/check_endpoint.py --base-url http://localhost:8000/v1 --model qwen3.6-35b \
      --anthropic --responses --parallel 4
  # Thinking models: either give them room (--max-tokens 1024) or disable thinking
  # (--no-think). From inside a container use http://host.docker.internal:<port>/v1.

Exit code is 0 only if no check FAILed.
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a UTF-8 text file from the repository and return its contents.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path of the file to read"}},
            "required": ["path"],
        },
    },
}
TOOL_PROMPT = "Use the read_file tool to read the file README.md. Do not answer from memory; call the tool."
RAW_MARKUP = ("<tool_call>", "<function=", "[TOOL_CALLS]", "<|tool_call", "\"name\": \"read_file\"")

results = []  # (check, status, latency_s, detail)


def record(check, status, latency, detail):
    results.append((check, status, latency, detail))


def http_json(url, body=None, headers=None, timeout=60.0):
    """POST (or GET if body is None) JSON; returns (status, parsed_json_or_text, seconds)."""
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="GET" if body is None else "POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode("utf-8", "replace"), e.code
    dt = time.time() - t0
    try:
        return status, json.loads(raw), dt
    except ValueError:
        return status, raw, dt


def short(x, n=90):
    s = x if isinstance(x, str) else json.dumps(x)
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[: n - 3] + "..."


class Checker:
    def __init__(self, a):
        self.a = a
        self.base = a.base_url.rstrip("/")
        self.root = (a.anthropic_base_url or (self.base[:-3] if self.base.endswith("/v1") else self.base)).rstrip("/")
        self.oa_headers = {"Authorization": f"Bearer {a.api_key}"}
        self.extra = json.loads(a.extra_body) if a.extra_body else {}
        if a.no_think:
            # vLLM / SGLang / llama.cpp honour chat_template_kwargs; Ollama's /v1 only honours
            # reasoning_effort="none" (verified on Ollama 0.40.6). Unknown keys are usually ignored,
            # but if a server rejects one, use --extra-body instead.
            if a.engine == "ollama":
                self.extra.setdefault("reasoning_effort", "none")
            else:
                self.extra.setdefault("chat_template_kwargs", {"enable_thinking": False})

    def chat_body(self, messages, **kw):
        b = {"model": self.a.model, "messages": messages, "max_tokens": self.a.max_tokens,
             "temperature": self.a.temperature}
        b.update(self.extra)
        b.update(kw)
        return b

    def post(self, path, body, headers=None):
        return http_json(self.base + path, body, {**self.oa_headers, **(headers or {})}, self.a.timeout)

    # ---- checks -------------------------------------------------------------
    def models(self):
        try:
            st, d, dt = http_json(self.base + "/models", None, self.oa_headers, self.a.timeout)
        except Exception as e:  # noqa: BLE001
            return record("models", "FAIL", None, f"server unreachable: {e}")
        if st != 200 or not isinstance(d, dict):
            return record("models", "WARN", dt, f"HTTP {st}: {short(d)}")
        ids = [m.get("id") for m in d.get("data", [])]
        ok = self.a.model in ids
        record("models", "PASS" if ok else "WARN", dt,
               f"model listed" if ok else f"'{self.a.model}' not in {short(ids, 60)}")

    def chat(self):
        st, d, dt = self.post("/chat/completions", self.chat_body(
            [{"role": "user", "content": "Reply with exactly one word: OK"}]))
        if st != 200 or not isinstance(d, dict) or not d.get("choices"):
            return record("chat", "FAIL", dt, f"HTTP {st}: {short(d)}")
        ch = d["choices"][0]
        m = ch.get("message", {})
        content = m.get("content") or ""
        reasoning = m.get("reasoning_content") or m.get("reasoning") or ""
        u = d.get("usage") or {}
        info = f"finish={ch.get('finish_reason')} out_tok={u.get('completion_tokens')}"
        if content.strip():
            record("chat", "PASS", dt, f"{short(content, 30)!r} {info}")
        elif reasoning:
            record("chat", "FAIL", dt, f"only reasoning, no content (thinking ate max_tokens? "
                                       f"raise --max-tokens or --no-think) {info}")
        else:
            record("chat", "FAIL", dt, f"empty content {info}")

    def tool_call(self):
        msgs = [{"role": "system", "content": "You are a coding agent. Use tools when asked."},
                {"role": "user", "content": TOOL_PROMPT}]
        st, d, dt = self.post("/chat/completions", self.chat_body(msgs, tools=[READ_FILE_TOOL]))
        if st != 200 or not isinstance(d, dict) or not d.get("choices"):
            record("tool_call", "FAIL", dt, f"HTTP {st}: {short(d)}")
            return record("tool_roundtrip", "SKIP", None, "no tool call")
        ch = d["choices"][0]
        m = ch.get("message", {})
        calls = m.get("tool_calls") or []
        content = m.get("content") or ""
        if not calls:
            hint = "raw tool markup in content -> wrong/missing --tool-call-parser" if any(
                t in content for t in RAW_MARKUP) else f"no tool_calls (finish={ch.get('finish_reason')})"
            record("tool_call", "FAIL", dt, f"{hint}: {short(content or m.get('reasoning') or '', 50)!r}")
            return record("tool_roundtrip", "SKIP", None, "no tool call")
        c = calls[0]
        fn = c.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}") if isinstance(fn.get("arguments"), str) else fn.get("arguments")
        except ValueError:
            args = None
        problems = []
        if fn.get("name") != "read_file":
            problems.append(f"name={fn.get('name')!r}")
        if not isinstance(args, dict) or "path" not in args:
            problems.append(f"bad arguments {short(str(fn.get('arguments')), 40)!r}")
        if not c.get("id"):
            problems.append("missing id")
        if problems:
            record("tool_call", "FAIL", dt, "; ".join(problems))
            return record("tool_roundtrip", "SKIP", None, "malformed tool call")
        record("tool_call", "PASS", dt, f"read_file({json.dumps(args)}) finish={ch.get('finish_reason')}")

        # round-trip: feed the tool result back
        msgs.append({"role": "assistant", "content": content or None, "tool_calls": [c]})
        msgs.append({"role": "tool", "tool_call_id": c.get("id"), "name": "read_file",
                     "content": "# demo-repo\nThe secret word is PINEAPPLE.\n"})
        msgs.append({"role": "user", "content": "What is the secret word in README.md? Answer in one word."})
        st, d, dt = self.post("/chat/completions", self.chat_body(msgs, tools=[READ_FILE_TOOL]))
        if st != 200 or not isinstance(d, dict) or not d.get("choices"):
            return record("tool_roundtrip", "FAIL", dt, f"HTTP {st}: {short(d)}")
        m = d["choices"][0].get("message", {})
        text = m.get("content") or ""
        if "PINEAPPLE" in text.upper():
            record("tool_roundtrip", "PASS", dt, f"{short(text, 40)!r}")
        elif text.strip() or m.get("tool_calls"):
            record("tool_roundtrip", "WARN", dt, f"accepted tool result but answer was {short(text or m, 40)!r}")
        else:
            record("tool_roundtrip", "FAIL", dt, "empty answer after tool result (raise --max-tokens?)")

    def anthropic(self):
        url = self.root + "/v1/messages"
        h = {"x-api-key": self.a.api_key, "anthropic-version": "2023-06-01"}
        body = {"model": self.a.model, "max_tokens": self.a.max_tokens,
                "messages": [{"role": "user", "content": "Reply with exactly one word: OK"}]}
        if self.a.no_think:
            body["thinking"] = {"type": "disabled"}
        try:
            st, d, dt = http_json(url, body, h, self.a.timeout)
        except Exception as e:  # noqa: BLE001
            return record("anthropic_text", "FAIL", None, str(e))
        if st != 200 or not isinstance(d, dict) or d.get("type") != "message":
            record("anthropic_text", "FAIL", dt, f"HTTP {st}: {short(d)}")
        else:
            types = [b.get("type") for b in d.get("content", [])]
            text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
            record("anthropic_text", "PASS" if text.strip() else "FAIL", dt,
                   f"blocks={types} stop={d.get('stop_reason')}" + ("" if text.strip() else " (no text block)"))
        tool = {"name": "read_file", "description": READ_FILE_TOOL["function"]["description"],
                "input_schema": READ_FILE_TOOL["function"]["parameters"]}
        body = {**body, "tools": [tool], "messages": [{"role": "user", "content": TOOL_PROMPT}]}
        st, d, dt = http_json(url, body, h, self.a.timeout)
        uses = [b for b in (d.get("content", []) if isinstance(d, dict) else []) if b.get("type") == "tool_use"]
        if st == 200 and uses and uses[0].get("name") == "read_file" and "path" in (uses[0].get("input") or {}):
            record("anthropic_tool", "PASS", dt, f"tool_use read_file({json.dumps(uses[0]['input'])})")
        else:
            record("anthropic_tool", "FAIL", dt, f"HTTP {st}: {short(d)}")

    def responses(self):
        body = {"model": self.a.model, "input": "Reply with exactly one word: OK",
                "max_output_tokens": self.a.max_tokens}
        if self.a.no_think:
            body["reasoning"] = {"effort": "none" if self.a.engine == "ollama" else "low"}
        st, d, dt = self.post("/responses", body)
        if st != 200 or not isinstance(d, dict) or "output" not in d:
            record("responses_text", "FAIL", dt, f"HTTP {st}: {short(d)}")
        else:
            types = [o.get("type") for o in d["output"]]
            text = "".join(c.get("text", "") for o in d["output"] if o.get("type") == "message"
                           for c in o.get("content", []))
            record("responses_text", "PASS" if text.strip() else "FAIL", dt,
                   f"output={types} status={d.get('status')}" + ("" if text.strip() else " (no output_text)"))
        f = READ_FILE_TOOL["function"]
        body = {**body, "input": TOOL_PROMPT,
                "tools": [{"type": "function", "name": f["name"], "description": f["description"],
                           "parameters": f["parameters"]}]}
        st, d, dt = self.post("/responses", body)
        calls = [o for o in (d.get("output", []) if isinstance(d, dict) else []) if o.get("type") == "function_call"]
        if st == 200 and calls and calls[0].get("name") == "read_file":
            record("responses_tool", "PASS", dt, f"function_call read_file({calls[0].get('arguments')})")
        else:
            record("responses_tool", "FAIL", dt, f"HTTP {st}: {short(d)}")

    def parallel(self, n):
        prompt = "Count from 1 to 200, separated by spaces. Output only the numbers."
        out = [None] * n

        def one(i):
            body = self.chat_body([{"role": "user", "content": prompt}], stream=True,
                                  stream_options={"include_usage": True})
            req = urllib.request.Request(self.base + "/chat/completions", json.dumps(body).encode(), method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {self.a.api_key}")
            t0, ttft, chunks, usage = time.time(), None, 0, None
            try:
                with urllib.request.urlopen(req, timeout=self.a.timeout) as r:
                    for line in r:
                        line = line.decode("utf-8", "replace").strip()
                        if not line.startswith("data:") or line == "data: [DONE]":
                            continue
                        ev = json.loads(line[5:])
                        usage = ev.get("usage") or usage
                        for ch in ev.get("choices", []):
                            delta = ch.get("delta", {})
                            if delta.get("content") or delta.get("reasoning_content") or delta.get("reasoning"):
                                chunks += 1
                                ttft = ttft or time.time() - t0
                out[i] = (time.time() - t0, ttft, (usage or {}).get("completion_tokens") or chunks, None)
            except Exception as e:  # noqa: BLE001
                out[i] = (time.time() - t0, None, 0, str(e))

        t0 = time.time()
        threads = [threading.Thread(target=one, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wall = time.time() - t0
        errs = [o[3] for o in out if o[3]]
        ok = [o for o in out if not o[3]]
        if not ok:
            return record(f"parallel x{n}", "FAIL", wall, f"all failed: {short(errs[0], 60)}")
        toks = sum(o[2] for o in ok)
        lat = sorted(o[0] for o in ok)
        ttfts = sorted(o[1] for o in ok if o[1] is not None)
        per_req = [o[2] / o[0] for o in ok if o[0] > 0]
        detail = (f"{len(ok)}/{n} ok, agg {toks / wall:.1f} tok/s, per-req {min(per_req):.1f}-{max(per_req):.1f} tok/s, "
                  f"lat p50 {lat[len(lat) // 2]:.1f}s max {lat[-1]:.1f}s"
                  + (f", TTFT max {ttfts[-1]:.2f}s" if ttfts else ""))
        # Queued requests show up as a staircase of TTFTs: the last one starts late.
        serial = n > 1 and len(ttfts) > 1 and ttfts[-1] > 0.5 * wall and ttfts[0] < 0.25 * ttfts[-1]
        if serial:
            detail += " | looks SERIALISED (check OLLAMA_NUM_PARALLEL / -np / --max-num-seqs)"
        record(f"parallel x{n}", "FAIL" if errs else ("WARN" if serial else "PASS"), wall,
               detail + (f"; errors: {short(errs[0], 40)}" if errs else ""))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", required=True, help="OpenAI-style base, e.g. http://localhost:8000/v1")
    p.add_argument("--model", required=True, help="model name as the server knows it")
    p.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", "dummy"))
    p.add_argument("--anthropic", action="store_true", help="also test Anthropic /v1/messages")
    p.add_argument("--anthropic-base-url", help="default: --base-url without trailing /v1")
    p.add_argument("--responses", action="store_true", help="also test OpenAI /v1/responses")
    p.add_argument("--parallel", type=int, default=0, metavar="N", help="N concurrent streamed requests")
    p.add_argument("--max-tokens", type=int, default=256, help="per request (thinking models need more)")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--timeout", type=float, default=120.0, help="seconds per request")
    p.add_argument("--no-think", action="store_true", help="ask the server to disable thinking")
    p.add_argument("--engine", choices=["auto", "ollama", "other"], default="auto",
                   help="only affects --no-think; auto = ollama if port 11434")
    p.add_argument("--extra-body", help='JSON merged into every chat request, e.g. \'{"top_k":20}\'')
    p.add_argument("--json-out", help="write results as JSON (for the run log)")
    a = p.parse_args()
    if a.engine == "auto":  # Ollama answers GET /api/version; others 404
        root = a.base_url.rstrip("/")
        root = root[:-3] if root.endswith("/v1") else root
        try:
            st, d, _ = http_json(root + "/api/version", None, None, 5)
            a.engine = "ollama" if st == 200 and isinstance(d, dict) and "version" in d else "other"
        except Exception:  # noqa: BLE001
            a.engine = "other"

    c = Checker(a)
    steps = [c.models, c.chat, c.tool_call]
    if a.anthropic:
        steps.append(c.anthropic)
    if a.responses:
        steps.append(c.responses)
    for step in steps:
        try:
            step()
        except Exception as e:  # noqa: BLE001  (timeouts, connection resets, ...)
            record(step.__name__, "FAIL", None, f"{type(e).__name__}: {e}")
    if a.parallel:
        try:
            c.parallel(a.parallel)
        except Exception as e:  # noqa: BLE001
            record(f"parallel x{a.parallel}", "FAIL", None, f"{type(e).__name__}: {e}")

    print(f"\nEndpoint {a.base_url}  model {a.model}\n")
    w = max(len(r[0]) for r in results)
    print(f"{'CHECK'.ljust(w)}  STATUS  {'TIME':>7}  DETAIL")
    print("-" * w + "  ------  -------  " + "-" * 50)
    for name, st, lat, det in results:
        print(f"{name.ljust(w)}  {st:<6}  {('%.2fs' % lat) if lat is not None else '-':>7}  {det}")
    n_fail = sum(r[1] == "FAIL" for r in results)
    print(f"\n{'ALL PASSED' if not n_fail else f'{n_fail} FAILED'}"
          f" ({sum(r[1] == 'WARN' for r in results)} warnings)")
    if a.json_out:
        with open(a.json_out, "w") as f:
            json.dump({"base_url": a.base_url, "model": a.model, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                       "args": vars(a), "results": [dict(zip(("check", "status", "seconds", "detail"), r))
                                                    for r in results]}, f, indent=2)
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
