"""Token accounting: the metering proxy (fake upstream, streaming and not) and the agy per-step parser."""

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from parbench.harnesses import get_harness
from parbench.meter import Meter

USAGE = {"prompt_tokens": 100, "completion_tokens": 7, "prompt_tokens_details": {"cached_tokens": 60},
         "completion_tokens_details": {"reasoning_tokens": 3}}


class _Upstream(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        if req.get("stream"):
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n')
            if (req.get("stream_options") or {}).get("include_usage"):
                self.wfile.write(f'data: {json.dumps({"choices": [], "usage": USAGE})}\n\n'.encode())
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            body = json.dumps({"choices": [{"message": {"content": "hi"}}], "usage": USAGE}).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def test_meter_counts_json_and_streams_and_flags_missing_usage():
    up = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    m = Meter(f"http://127.0.0.1:{up.server_address[1]}/v1")
    try:
        m.attach("a", None)
        for body in ({}, {"stream": True, "stream_options": {"include_usage": True}}, {"stream": True}):
            req = urllib.request.Request(m.url_for("a") + "/chat/completions", headers={"Content-Type": "application/json"},
                                         data=json.dumps({"model": "x", "messages": [], **body}).encode())
            out = urllib.request.urlopen(req).read()
            assert b"hi" in out  # response passed through unchanged
        s = m.summary("a")
        assert s["requests"] == 3 and s["requests_usage_missing"] == 1
        assert s["usage"]["input"] == 200 and s["usage"]["cached_input"] == 120
        assert s["usage"]["output"] == 14 and s["usage"]["reasoning"] == 6 and s["usage"]["calls"] == 2
    finally:
        m.close()
        up.shutdown()


def _agy_attempt(conv, steps, cum):
    lines = [{"event": "step_update", "step_update": {"conversation_id": conv, "step_index": i, "usage": u}}
             for i, u in steps]
    lines.append({"event": "result", "result": {"conversation_id": conv, "status": "SUCCESS", "usage": cum}})
    return "\n".join(json.dumps(x) for x in lines)


def test_agy_counts_steps_not_the_conversation_running_total():
    h = get_harness("agy")
    u = lambda i, c, o: {"input_tokens": i, "cache_read_tokens": c, "output_tokens": o, "thinking_tokens": 0}
    a0 = h.parse(_agy_attempt("c", [(1, u(100, 0, 5)), (3, u(10, 100, 5))], u(110, 100, 10)), "")
    # resumed attempt: result.usage includes attempt 0 again
    a1 = h.parse(_agy_attempt("c", [(5, u(20, 200, 4))], u(130, 300, 14)), "")
    assert (a0.usage.input, a0.usage.cached_input, a0.usage.output) == (210, 100, 10)
    assert (a1.usage.input, a1.usage.cached_input, a1.usage.output) == (220, 200, 4)
    assert a1.usage_session_total.input == 430  # = a0 + a1: the running total
