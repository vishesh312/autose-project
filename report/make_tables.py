"""Build report/tables.tex from results/core_agy (valid runs only). Re-run before compiling the report."""
import collections, glob, json, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = {"gemini-flash-agy": "Gemini 3.8 Flash", "gpt-oss-120b-agy": "GPT-OSS 120B"}
rows = collections.defaultdict(list)
invalid = 0
for f in glob.glob(str(ROOT / "results/core_agy/*/run.json")):
    d = json.load(open(f))
    if not d.get("valid", True):
        invalid += 1
        continue
    r, c = d["run"], d["correctness"]
    p = c["by_final"][c["primary"]]
    m = d.get("merge") or {}
    rows[(r["model"], r["strategy"])].append(dict(
        pass_rate=p["task_pass_rate"], bundle=1.0 if p["bundle_success"] else 0.0,
        wall=d["time"]["wall_clock_s"], tok=d["cost"]["usage"]["input"], conflict=m.get("conflict_rate")))

lines = [r"\begin{tabular}{@{}llrcccc@{}}", r"\toprule",
         r"Model & Strat. & $n$ & Task pass & Bundle & Wall (s) & In-tokens (M) \\", r"\midrule"]
for model in ("gemini-flash-agy", "gpt-oss-120b-agy"):
    for s in ("S0", "S1", "S2", "S4"):
        v = rows.get((model, s))
        if not v:
            continue
        conf = [x["conflict"] for x in v if x["conflict"] is not None]
        lines.append(f"{NAME[model]} & {s} & {len(v)} & {statistics.mean(x['pass_rate'] for x in v):.2f} & "
                     f"{statistics.mean(x['bundle'] for x in v):.2f} & {statistics.median(x['wall'] for x in v):.0f} & "
                     f"{statistics.median(x['tok'] for x in v)/1e6:.1f} \\\\")
    lines.append(r"\midrule" if model == "gemini-flash-agy" else "")
lines = [l for l in lines if l != ""]
if lines[-1] == r"\midrule":
    lines.pop()
lines += [r"\bottomrule", r"\end{tabular}"]
(ROOT / "report/tables.tex").write_text("\n".join(lines) + "\n")
total = sum(len(v) for v in rows.values())
(ROOT / "report/stats.tex").write_text(f"\\newcommand{{\\validruns}}{{{total}}}\n\\newcommand{{\\invalidruns}}{{{invalid}}}\n")
print("valid", total, "invalid", invalid)


# ---- per-pool table (task pass fraction per run; "-" = no valid run yet)
POOL = {"task8563": "dspy 8563", "task27": "go\\_chi 27", "task2800": "click 2800", "task1559": "jinja 1559", "task1621": "jinja 1621"}
per = collections.defaultdict(dict)
for f in glob.glob(str(ROOT / "results/core_agy/*/run.json")):
    d = json.load(open(f))
    if not d.get("valid", True):
        continue
    r, c = d["run"], d["correctness"]
    per[(r["model"], r["strategy"])][r["pool"].split("/")[1]] = c["by_final"][c["primary"]]["task_pass_rate"]
cols = [(m, s) for m in ("gemini-flash-agy", "gpt-oss-120b-agy") for s in ("S0", "S1", "S2", "S4")]
out = [r"\begin{tabular}{@{}l" + "c" * 4 + "c" * 4 + r"@{}}", r"\toprule",
       r" & \multicolumn{4}{c}{Gemini 3.8 Flash} & \multicolumn{4}{c}{GPT-OSS 120B} \\",
       r"\cmidrule(lr){2-5}\cmidrule(lr){6-9}", r"Pool & S0 & S1 & S2 & S4 & S0 & S1 & S2 & S4 \\", r"\midrule"]
for key, label in POOL.items():
    cells = []
    for col in cols:
        v = per[col].get(key)
        cells.append("--" if v is None else f"{v:.1f}")
    out.append(label + " & " + " & ".join(cells) + r" \\")
out += [r"\bottomrule", r"\end{tabular}"]
(ROOT / "report/tables_pool.tex").write_text("\n".join(out) + "\n")


# ---- macros for the numbers quoted in the text (so prose and tables cannot drift apart)
import datetime
NAMES = {"S0": "Zero", "S1": "One", "S2": "Two", "S4": "Four"}
mac = [f"\\newcommand{{\\asof}}{{{datetime.datetime.now().strftime('%-d %b, %H:%M')} IST}}"]
par = {}
for f in glob.glob(str(ROOT / "results/core_agy/*/run.json")):
    d = json.load(open(f))
    if d.get("valid", True) and d["run"]["model"] == "gemini-flash-agy":
        par.setdefault(d["run"]["strategy"], []).append((d["time"]["effective_parallelism"], (d.get("merge") or {}).get("conflict_rate")))
for st, nm in NAMES.items():
    v = rows.get(("gemini-flash-agy", st), [])
    if not v:
        mac += [f"\\newcommand{{\\gem{nm}{k}}}{{--}}" for k in ("N", "P", "W", "T", "Par", "C")]
        continue
    pars = [p for p, _ in par.get(st, [])]
    confs = [c for _, c in par.get(st, []) if c is not None]
    mac += [f"\\newcommand{{\\gem{nm}N}}{{{len(v)}}}",
            f"\\newcommand{{\\gem{nm}P}}{{{statistics.mean(x['pass_rate'] for x in v):.2f}}}",
            f"\\newcommand{{\\gem{nm}W}}{{{statistics.median(x['wall'] for x in v):.0f}}}",
            f"\\newcommand{{\\gem{nm}T}}{{{statistics.median(x['tok'] for x in v)/1e6:.1f}}}",
            f"\\newcommand{{\\gem{nm}Par}}{{{statistics.mean(pars):.2f}}}" if pars else f"\\newcommand{{\\gem{nm}Par}}{{--}}",
            f"\\newcommand{{\\gem{nm}C}}{{{statistics.mean(confs):.2f}}}" if confs else f"\\newcommand{{\\gem{nm}C}}{{--}}"]
g0 = rows.get(("gemini-flash-agy", "S0")); g1 = rows.get(("gemini-flash-agy", "S1"))
if g0 and g1:
    t0, t1 = statistics.median(x["tok"] for x in g0), statistics.median(x["tok"] for x in g1)
    mac += [f"\\newcommand{{\\tokRatio}}{{{t0/t1:.1f}}}", f"\\newcommand{{\\tokLow}}{{{t1/2e6:.0f}}}", f"\\newcommand{{\\tokHigh}}{{{t0/2e6:.0f}}}"]
with open(ROOT / "report/stats.tex", "a") as fh:
    fh.write("\n".join(mac) + "\n")
