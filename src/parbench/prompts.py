"""Prompt templates live in prompts/*.md and use ${name} placeholders (string.Template)."""

from __future__ import annotations

from string import Template

from .config import ROOT
from .dataset import Feature

PROMPT_DIR = ROOT / "prompts"


def template(name: str) -> str:
    return (PROMPT_DIR / f"{name}.md").read_text()


def render(name: str, **kw) -> str:
    repo = kw.pop("repo", "/workspace/repo")
    kw.setdefault("preamble", Template(template("preamble")).safe_substitute(repo=repo).strip())
    return Template(template(name)).safe_substitute(**{k: str(v) for k, v in kw.items()}).strip() + "\n"


def tasks_block(features: list[Feature]) -> str:
    return "\n\n".join(f"### Task {i}\n\n{f.description.strip()}" for i, f in enumerate(features, 1))


def single_task(feature: Feature, extra: str | None = None, repo: str = "/workspace/repo") -> str:
    task = feature.description.strip()
    if extra:
        task += "\n\n" + template(extra).strip()
    return render("single_task", task=task, repo=repo)


def multi_task(features: list[Feature], name: str = "multi_task", extra: str | None = None,
               repo: str = "/workspace/repo") -> str:
    out = render(name, k=len(features), tasks=tasks_block(features), repo=repo)
    if extra:
        out += "\n" + template(extra).strip() + "\n"
    return out


def resolver(features: list[Feature], conflict_files: list[str], repo: str = "/workspace/repo") -> str:
    return render(
        "resolver",
        repo=repo,
        tasks=tasks_block(features),
        conflict_files="\n".join(f"- {f}" for f in conflict_files),
    )
