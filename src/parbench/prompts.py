"""Prompt templates live in prompts/*.md and use ${name} placeholders (string.Template)."""

from __future__ import annotations

from string import Template

from .config import ROOT
from .dataset import Feature

PROMPT_DIR = ROOT / "prompts"


def template(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text()


def render(name: str, **kw) -> str:
    repo = kw.setdefault("repo", "/workspace/repo")  # keep it in kw: nudge, resolver and S4 templates use ${repo} too
    kw.setdefault("preamble", Template(template("preamble")).safe_substitute(repo=repo).strip())
    return Template(template(name)).safe_substitute(**{k: str(v) for k, v in kw.items()}).strip() + "\n"


def tasks_block(features: list[Feature]) -> str:
    return "\n\n".join(f"### Task {i}\n\n{f.description.strip()}" for i, f in enumerate(features, 1))


def _extras(extra: str | list[str] | None) -> str:
    """Prompt snippets named by `+extra` in the strategy spec (all of them, in order)."""
    names = [extra] if isinstance(extra, str) else (extra or [])
    return "\n\n".join(template(n).strip() for n in names)


def single_task(feature: Feature, extra: str | list[str] | None = None, repo: str = "/workspace/repo") -> str:
    task = feature.description.strip()
    if extra:
        task += "\n\n" + _extras(extra)
    return render("single_task", task=task, repo=repo)


def multi_task(features: list[Feature], name: str = "multi_task", extra: str | list[str] | None = None,
               repo: str = "/workspace/repo") -> str:
    out = render(name, k=len(features), tasks=tasks_block(features), repo=repo)
    if extra:
        out += "\n" + _extras(extra) + "\n"
    return out


def resolver(features: list[Feature], conflict_files: list[str], repo: str = "/workspace/repo") -> str:
    return render(
        "resolver",
        repo=repo,
        tasks=tasks_block(features),
        conflict_files="\n".join(f"- {f}" for f in conflict_files),
    )


def planner(features: list[Feature], repo: str = "/workspace/repo") -> str:
    """S3 planner: tasks are labelled by feature id (f1, f4, ...) so the plan can name them unambiguously."""
    tasks = "\n\n".join(f"### Task f{f.fid}\n\n{f.description.strip()}" for f in features)
    return render("planner", repo=repo, k=len(features), tasks=tasks, ids=", ".join(f"f{f.fid}" for f in features))
