"""Generate the toy smoke-test pool in CooperBench layout: smoke/dataset/toy_task/task1/.

    python smoke/build_toy_dataset.py && parbench build-toy

Repo: `textkit`, a tiny Python text-stats package. Six features with KNOWN conflict structure:
  f1 lines op      } both add a function + an OPERATIONS entry at the same spot -> conflict
  f2 unique op     }
  f3 --json flag   } both edit the same lines of cli.py -> conflict
  f4 stdin input   }
  f5 slugify       new module, independent
  f6 word_count ignores punctuation tokens: edits core.py, but away from f1/f2's hunk -> clean
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).parent
POOL = HERE / "dataset" / "toy_task" / "task1"
IMAGE = "parbench-toy-textkit:task1"

# ----------------------------------------------------------------------------- base repo
CORE = '''"""Core text operations."""


def word_count(text: str) -> int:
    """Number of whitespace-separated words."""
    return len(text.split())


def char_count(text: str) -> int:
    """Number of characters, including whitespace."""
    return len(text)


OPERATIONS = {
    "words": word_count,
    "chars": char_count,
}


def run(op: str, text: str):
    """Apply the named operation to text."""
    if op not in OPERATIONS:
        raise KeyError(f"unknown operation: {op}")
    return OPERATIONS[op](text)
'''

CLI = '''"""Command line interface: textkit OP FILE"""

import argparse
import sys

from .core import OPERATIONS, run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="textkit")
    parser.add_argument("op", choices=sorted(OPERATIONS))
    parser.add_argument("file")
    args = parser.parse_args(argv)
    with open(args.file) as fh:
        text = fh.read()
    result = run(args.op, text)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

BASE = {
    "textkit/__init__.py": '"""textkit: tiny text statistics."""\n\n__version__ = "0.1.0"\n',
    "textkit/core.py": CORE,
    "textkit/cli.py": CLI,
    "pyproject.toml": '[project]\nname = "textkit"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n\n'
                      '[project.scripts]\ntextkit = "textkit.cli:main"\n\n[build-system]\n'
                      'requires = ["setuptools>=61"]\nbuild-backend = "setuptools.build_meta"\n\n'
                      '[tool.setuptools]\npackages = ["textkit"]\n',
    ".gitignore": "__pycache__/\n*.egg-info/\n.pytest_cache/\nbuild/\n",
    "README.md": "# textkit\n\nTiny text statistics. `textkit words FILE`, `textkit chars FILE`.\n"
                 "Run tests with `python -m pytest tests`.\n",
    "tests/test_core.py": '''from textkit.core import char_count, run, word_count


def test_word_count():
    assert word_count("a b  c") == 3


def test_char_count():
    assert char_count("ab c") == 4


def test_run():
    assert run("words", "x y") == 2
''',
}

# ----------------------------------------------------------------------------- features
F1_FUNC = '''

def line_count(text: str) -> int:
    """Number of lines; a trailing newline does not start a new line."""
    return len(text.splitlines())
'''
F2_FUNC = '''

def unique_words(text: str) -> int:
    """Number of distinct words, compared case-insensitively."""
    return len({w.lower() for w in text.split()})
'''
F6_WC = '''def word_count(text: str) -> int:
    """Number of whitespace-separated words. Tokens with no letter or digit (e.g. "--") are ignored."""
    return len([w for w in text.split() if any(ch.isalnum() for ch in w)])'''
BASE_WC = '''def word_count(text: str) -> int:
    """Number of whitespace-separated words."""
    return len(text.split())'''
CC_END = '    return len(text)\n'


def core_with(f1=False, f2=False, f6=False) -> str:
    s = CORE
    funcs = (F1_FUNC if f1 else "") + (F2_FUNC if f2 else "")
    s = s.replace(CC_END, CC_END + funcs, 1)
    entries = ('    "lines": line_count,\n' if f1 else "") + ('    "unique": unique_words,\n' if f2 else "")
    s = s.replace('    "chars": char_count,\n', '    "chars": char_count,\n' + entries, 1)
    if f6:
        s = s.replace(BASE_WC, F6_WC, 1)
    return s


def cli_with(f3=False, f4=False) -> str:
    s = CLI
    if f3:
        s = s.replace("import argparse\n", "import argparse\nimport json\n", 1)
    file_line = '    parser.add_argument("file", help="input file, or - to read standard input")\n' if f4 \
        else '    parser.add_argument("file")\n'
    json_line = '    parser.add_argument("--json", action="store_true", help="print the result as JSON")\n' if f3 else ""
    s = s.replace('    parser.add_argument("file")\n', file_line + json_line, 1)
    if f4:
        s = s.replace(
            "    with open(args.file) as fh:\n        text = fh.read()\n",
            '    if args.file == "-":\n        text = sys.stdin.read()\n    else:\n'
            "        with open(args.file) as fh:\n            text = fh.read()\n", 1)
    if f3:
        s = s.replace("    print(result)\n",
                      '    if args.json:\n        print(json.dumps({"op": args.op, "result": result}))\n'
                      "    else:\n        print(result)\n", 1)
    return s


SLUG = '''"""URL slugs."""

import re


def slugify(text: str, sep: str = "-") -> str:
    """Lowercase, replace runs of non-alphanumeric characters with `sep`, strip leading/trailing `sep`."""
    slug = re.sub(r"[^a-z0-9]+", sep, text.lower())
    return slug.strip(sep)
'''

FEATURES = {
    1: dict(
        md="""**Title**: Add a `lines` operation

**Description**: Add a `line_count(text)` function to `textkit/core.py` that returns the number of lines in the text. A trailing newline must not count as an extra line (`"a\\nb\\n"` has 2 lines, `""` has 0). Register it in `OPERATIONS` under the name `"lines"` so that `textkit lines FILE` works from the CLI.
""",
        files={"textkit/core.py": core_with(f1=True)},
        tests={"tests/test_f1_lines.py": '''from textkit.cli import main
from textkit.core import OPERATIONS, line_count, run


def test_line_count():
    assert line_count("a\\nb\\n") == 2
    assert line_count("a\\nb") == 2
    assert line_count("") == 0


def test_registered():
    assert "lines" in OPERATIONS
    assert run("lines", "x\\ny\\nz\\n") == 3


def test_cli(tmp_path, capsys):
    p = tmp_path / "t.txt"
    p.write_text("one\\ntwo\\n")
    assert main(["lines", str(p)]) == 0
    assert capsys.readouterr().out.strip() == "2"
'''},
    ),
    2: dict(
        md="""**Title**: Add a `unique` operation

**Description**: Add a `unique_words(text)` function to `textkit/core.py` that returns the number of distinct whitespace-separated words, compared case-insensitively (`"The the THE cat"` has 2 unique words). Register it in `OPERATIONS` under the name `"unique"` so that `textkit unique FILE` works from the CLI.
""",
        files={"textkit/core.py": core_with(f2=True)},
        tests={"tests/test_f2_unique.py": '''from textkit.cli import main
from textkit.core import OPERATIONS, run, unique_words


def test_unique_words():
    assert unique_words("The the THE cat") == 2
    assert unique_words("") == 0


def test_registered():
    assert "unique" in OPERATIONS
    assert run("unique", "a b a") == 2


def test_cli(tmp_path, capsys):
    p = tmp_path / "t.txt"
    p.write_text("x X y")
    assert main(["unique", str(p)]) == 0
    assert capsys.readouterr().out.strip() == "2"
'''},
    ),
    3: dict(
        md="""**Title**: Add a `--json` output flag to the CLI

**Description**: Add a `--json` flag to `textkit` (`textkit/cli.py`). When given, print a single JSON object `{"op": <operation name>, "result": <result>}` instead of the plain result. Without the flag, output is unchanged.
""",
        files={"textkit/cli.py": cli_with(f3=True)},
        tests={"tests/test_f3_json.py": '''import json

from textkit.cli import main


def test_json_flag(tmp_path, capsys):
    p = tmp_path / "t.txt"
    p.write_text("a b c")
    assert main(["words", str(p), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"op": "words", "result": 3}


def test_plain_unchanged(tmp_path, capsys):
    p = tmp_path / "t.txt"
    p.write_text("a b c")
    assert main(["words", str(p)]) == 0
    assert capsys.readouterr().out.strip() == "3"
'''},
    ),
    4: dict(
        md="""**Title**: Read from standard input when the file is `-`

**Description**: In `textkit/cli.py`, when the FILE argument is `-`, read the text from standard input instead of opening a file. Update the argument's help text to say so. Behaviour for real file paths is unchanged.
""",
        files={"textkit/cli.py": cli_with(f4=True)},
        tests={"tests/test_f4_stdin.py": '''import io
import sys

from textkit.cli import main


def test_stdin(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("one two three four"))
    assert main(["words", "-"]) == 0
    assert capsys.readouterr().out.strip() == "4"


def test_file_still_works(tmp_path, capsys):
    p = tmp_path / "t.txt"
    p.write_text("ab")
    assert main(["chars", str(p)]) == 0
    assert capsys.readouterr().out.strip() == "2"
'''},
    ),
    5: dict(
        md="""**Title**: Add a `slugify` helper

**Description**: Add a new module `textkit/slug.py` with a function `slugify(text, sep="-")` that lowercases the text, replaces every run of characters that are not ASCII letters or digits with `sep`, and strips leading/trailing separators. Example: `slugify("  Hello, World!! ")` returns `"hello-world"`, and `slugify("A B", sep="_")` returns `"a_b"`.
""",
        files={"textkit/slug.py": SLUG},
        tests={"tests/test_f5_slug.py": '''from textkit.slug import slugify


def test_basic():
    assert slugify("  Hello, World!! ") == "hello-world"


def test_sep():
    assert slugify("A B", sep="_") == "a_b"


def test_empty():
    assert slugify("!!!") == ""
'''},
    ),
    6: dict(
        md="""**Title**: Ignore punctuation-only tokens in word counts

**Description**: Change `word_count` in `textkit/core.py` so that whitespace-separated tokens containing no letter or digit (such as `"--"` or `"..."`) are not counted as words. `"hello -- world ..."` has 2 words; `"it's 2 o'clock"` still has 3.
""",
        files={"textkit/core.py": core_with(f6=True)},
        tests={"tests/test_f6_punct.py": '''from textkit.core import run, word_count


def test_punct_ignored():
    assert word_count("hello -- world ...") == 2


def test_apostrophes_kept():
    assert word_count("it's 2 o'clock") == 3


def test_via_run():
    assert run("words", "a , b") == 2
'''},
    ),
}

COMBINED = {
    "textkit/core.py": core_with(f1=True, f2=True, f6=True),
    "textkit/cli.py": cli_with(f3=True, f4=True),
    "textkit/slug.py": SLUG,
}

DOCKERFILE = f'''# Toy pool image, same contract as CooperBench images: repo at /workspace/repo (HEAD = base),
# grader at /usr/local/bin/runner.sh <tests.patch> [feature.patch] with patches under /patches.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \\
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir pytest
COPY repo /workspace/repo
WORKDIR /workspace/repo
RUN git init -q && git add -A \\
    && GIT_AUTHOR_DATE=2026-01-01T00:00:00Z GIT_COMMITTER_DATE=2026-01-01T00:00:00Z \\
       git -c user.name=toy -c user.email=toy@local commit -qm base \\
    && pip install --no-cache-dir -e . && git status --porcelain
COPY runner.sh /usr/local/bin/runner.sh
RUN chmod +x /usr/local/bin/runner.sh
'''

RUNNER = r'''#!/bin/bash
# Toy grader with the CooperBench runner.sh contract.
set -e
TEST_PATCH="$1"
FEATURE_PATCH="$2"
cd /workspace/repo
git reset -q --hard HEAD
git clean -fdxq
if [[ -n "$FEATURE_PATCH" ]]; then
  git apply --ignore-whitespace "/patches/$FEATURE_PATCH" || git apply --3way "/patches/$FEATURE_PATCH"
fi
git apply --ignore-whitespace "/patches/$TEST_PATCH" || git apply --3way "/patches/$TEST_PATCH"
pip install -q --no-deps -e . >/dev/null 2>&1 || true
TEST_FILES=$(grep -oE '^\+\+\+ b/[^ ]+\.py' "/patches/$TEST_PATCH" | sed 's#^+++ b/##')
python -m pytest $TEST_FILES -v
'''


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)


def diff_for(base_dir: Path, files: dict[str, str]) -> str:
    """Patch (vs base) that turns base into base+files."""
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td) / "r"
        shutil.copytree(base_dir, wd)
        write_tree(wd, files)
        git(wd, "add", "-A")
        return git(wd, "diff", "--cached", "HEAD")


def main() -> None:
    if POOL.exists():
        shutil.rmtree(POOL)
    (POOL / "repo").mkdir(parents=True)
    write_tree(POOL / "repo", BASE)
    (POOL / "IMAGE").write_text(IMAGE + "\n")
    (POOL / "Dockerfile").write_text(DOCKERFILE)
    (POOL / "runner.sh").write_text(RUNNER)

    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "base"
        shutil.copytree(POOL / "repo", base)
        git(base, "init", "-q")
        git(base, "add", "-A")
        git(base, "-c", "user.name=toy", "-c", "user.email=toy@local", "commit", "-qm", "base")
        for fid, f in FEATURES.items():
            d = POOL / f"feature{fid}"
            d.mkdir()
            (d / "feature.md").write_text(f["md"])
            (d / "feature.patch").write_text(diff_for(base, f["files"]))
            (d / "tests.patch").write_text(diff_for(base, f["tests"]))
        (POOL / "combined.patch").write_text(diff_for(base, COMBINED))

        # gold pairwise conflict report, same schema as CooperBench's
        results = []
        for a, b in combinations(sorted(FEATURES), 2):
            wd = Path(td) / f"m{a}{b}"
            shutil.copytree(base, wd)
            for n, fid in (("a", a), ("b", b)):
                git(wd, "checkout", "-q", "-B", n, "master" if "master" in git(wd, "branch") else "main")
                write_tree(wd, FEATURES[fid]["files"])
                git(wd, "add", "-A")
                git(wd, "-c", "user.name=t", "-c", "user.email=t@l", "commit", "-qm", n)
            git(wd, "checkout", "-q", "a")
            r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@l", "merge", "-q", "--no-edit", "b"],
                               cwd=wd, capture_output=True, text=True)
            results.append({"repo": "toy_task", "task_id": 1, "f1": a, "f2": b, "has_conflict": r.returncode != 0})
    conflicts = [r for r in results if r["has_conflict"]]
    (HERE / "dataset" / "gold_conflict_report.json").write_text(json.dumps({
        "summary": {"total_pairs": len(results), "conflicts": len(conflicts)},
        "conflict_pairs": conflicts, "all_results": results}, indent=2))
    print(f"wrote {POOL}; gold conflicts: {[(r['f1'], r['f2']) for r in conflicts]}")


if __name__ == "__main__":
    main()
