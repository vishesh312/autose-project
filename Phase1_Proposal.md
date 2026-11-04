# Phase 1: Proposal

### 1. Problem Statement and Motivation

Software engineering agents are becoming increasingly capable, but when multiple tasks are assigned to a model or when multiple agents work in parallel there is a significant amount of compute and effort wasted during the merging process. When tasks conflict by touching the same files, uncoordinated agents often duplicate work, re-explore identical context, or generate inconsistent outputs. Currently, there is no comprehensive benchmark designed to measure a harness or model's efficiency and capability when handling multiple, potentially conflicting tasks at once.

### 2. Existing Approaches

Recent works have started exploring this area, but they leave significant gaps:

- **CooperBench:** Evaluates two agents cooperating on a task, but it relies entirely on hand-written datasets and only tests one specific harness framework without comparing alternatives.
- **NP-Bench:** Compares uncoordinated agents against up-front planning, but it contains only a very small set of 9 hand-built scenarios.
- **General limitations:** Other studies note the hidden costs of parallelism (like workers reconciling inconsistent outputs), but existing benchmarks either force sequential work, assign tasks to fixed peers, or lack the ability to scale to more than two tasks with a controllable amount of conflict.

### 3. Objectives and Scope

Our objective is to build a benchmark and evaluation pipeline that measures how well different agentic harnesses handle multiple overlapping tasks, focusing heavily on resource efficiency and wasted effort.

- **In Scope:** Creating automatic bundles of concurrent tasks from existing datasets and evaluating various harness orchestration strategies (e.g., sequential, naive parallel fan-out, and upfront planning) against these bundles.
- **Out of Scope:** We will not be developing an entirely new foundational LLM or a completely new orchestration framework from scratch; the core contribution is the benchmarking pipeline and the comparative evaluation of orchestration strategies.

### 4. Proposed Direction

We will construct this benchmark by automatically bundling existing single-task or dual-task benchmarks into larger $k$-task groups.

- **Dataset Construction:** We will start by re-bundling features from CooperBench into larger groups that share a single repository snapshot and a known joint gold solution. If time permits, we will also bundle SWE-smith bugs to create datasets with an adjustable "conflict density" dial.
- **Evaluation:** We will run multiple harness configurations such as sequential execution, naive fan-out with an LLM resolver, and a predict-then-schedule approach to evaluate which architectures best mitigate merge conflicts and wasted effort. We will also utilize existing frontier models(Claude, Codex etc) for this task.

### 5. Success & Quality Attributes

We will evaluate the harnesses using metrics that balance functional success with resource efficiency:

- **Correctness & Interference:** The resolution rate of all tasks on the final merged tree, and the performance retention when running tasks together versus in isolation.
- **Cost & Waste:** The total input and output tokens used, lines edited by multiple agents, and the effort/tokens wasted on discarded patches.
- **Latency & Parallelism:** End-to-end wall-clock time compared against the total agent-busy time.
- **Planning Quality:** How accurately the harness predicts file scopes to avoid conflicts prior to execution.