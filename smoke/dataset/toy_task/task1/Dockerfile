# Toy pool image, same contract as CooperBench images: repo at /workspace/repo (HEAD = base),
# grader at /usr/local/bin/runner.sh <tests.patch> [feature.patch] with patches under /patches.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir pytest
COPY repo /workspace/repo
WORKDIR /workspace/repo
RUN git init -q && git add -A \
    && GIT_AUTHOR_DATE=2026-01-01T00:00:00Z GIT_COMMITTER_DATE=2026-01-01T00:00:00Z \
       git -c user.name=toy -c user.email=toy@local commit -qm base \
    && pip install --no-cache-dir -e . && git status --porcelain
COPY runner.sh /usr/local/bin/runner.sh
RUN chmod +x /usr/local/bin/runner.sh
