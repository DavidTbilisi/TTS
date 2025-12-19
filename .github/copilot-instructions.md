# Copilot Instructions: Architecture Corrections for `TTS_ka`

## Goal

Refactor and correct architectural inconsistencies in the `TTS_ka` repository **without changing external behavior**, CLI flags, or public APIs unless explicitly stated.

Focus on **clarity, correctness, and maintainability**, not feature additions.

---

## Global Rules

1. **Do not break CLI compatibility**
2. **Do not rename public facade functions** unless instructed
3. **Prefer consolidation over proliferation**
4. **If a module has no clear responsibility, remove or merge it**
5. **Update Mermaid diagrams and docs after code changes**

---

## Task 1: Resolve `chunking.py` vs `chunker.py`

### Problem

Both files exist but represent overlapping responsibilities.

### Instructions

* Inspect `chunking.py` and `chunker.py`
* Choose ONE of the following strategies and implement it consistently:

**Option A (Preferred):**

* `chunking.py` → high-level logic (heuristics, chunk size, limits)
* `chunker.py` → pure text splitting function(s)

**Option B:**

* Merge all logic into `chunking.py`
* Delete `chunker.py`
* Update all imports and references

### Acceptance Criteria

* Only one clear text-chunking API
* No duplicated logic
* All callers use the same module

---

## Task 2: Clarify or Eliminate `core.py`

### Problem

`core.py` is referenced in diagrams but not in workflows.

### Instructions

* Analyze whether `core.py` is:

  * a real orchestration layer, or
  * a thin utility wrapper

Then do ONE of the following:

**Option A (Promote):**

* Route `facades.py`, `cli.py`, and `main.py` through `core.py`
* Make `core.py` the single orchestration entry

**Option B (Remove):**

* Inline or relocate logic
* Remove `core.py`
* Update imports and docs

### Acceptance Criteria

* No “ghost” core module
* Architecture diagrams match reality

---

## Task 3: Fix Misleading Naming (“Ultra-fast”)

### Problem

Short-text generation is labeled “ultra-fast” but uses `fast_audio`.

### Instructions

* Rename internal concepts only (not public CLI flags unless safe):

  * “Ultra-fast” → **parallel / chunked**
  * “Fast” → **direct**

Examples:

* `ultra_fast_parallel_generation` → `parallel_generate_chunks`
* `smart_generate_long_text` → `generate_long_text`

### Acceptance Criteria

* Names reflect actual behavior
* Public API compatibility preserved

---

## Task 4: Make Async Boundary Explicit in `facades.py`

### Problem

`facades.py` uses `asyncio.run`, which breaks in active event loops.

### Instructions

* Add explicit docstrings and comments stating:

  * Facades are **sync-only**
  * Not safe inside running event loops (Jupyter, FastAPI, etc.)
* If feasible:

  * Expose internal async functions clearly (no behavior change)

### Acceptance Criteria

* No ambiguity about async usage
* Clear warnings for advanced users

---

## Task 5: Make `not_reading.py` Mandatory in Flows

### Problem

Text sanitization appears optional in diagrams but is required.

### Instructions

* Ensure all generation paths explicitly call text sanitization
* Add a single entry function (e.g. `sanitize_text`)
* Call it:

  * in CLI
  * in facades
  * before chunking

### Acceptance Criteria

* No generation path skips sanitization
* Single sanitization API

---

## Task 6: Fix Streaming Workflow Logic

### Problem

Streaming output logic differs by OS but diagrams assume merge always happens.

### Instructions

* Add conditional logic:

  * Merge only if required
  * Document Windows vs Unix behavior
* Update Mermaid diagram to include decision node:

  * `merge needed?`

### Acceptance Criteria

* Code and docs agree
* Platform differences are explicit

---

## Task 7: Add Error-Handling Paths (Minimal)

### Problem

Failure cases are undocumented and partially unhandled.

### Instructions

* Add minimal, explicit error paths:

  * chunk failure
  * merge failure
  * streaming failure
* Prefer retries + fallback where already used
* Do NOT add complex recovery logic

### Acceptance Criteria

* Errors propagate clearly
* No silent failures

---

## Task 8: Update Architecture Documentation

### Instructions

* Update all Mermaid diagrams to reflect:

  * module removals/merges
  * corrected naming
  * sanitization flow
  * streaming merge decision
* Ensure diagrams match code **exactly**

### Acceptance Criteria

* No diagram references non-existent modules
* Names and flows are accurate

---

## Non-Goals (Do NOT Do These)

* ❌ No new features
* ❌ No performance tuning
* ❌ No CLI UX changes
* ❌ No dependency changes unless required

---

## Final Validation Checklist

Before marking complete:

* [ ] CLI still works
* [ ] Facades still work
* [ ] Long + short text generation unchanged
* [ ] Streaming still functions
* [ ] Diagrams render correctly
* [ ] No unused modules remain

---

### Tone Reminder for Copilot

> Be conservative. Refactor like a senior maintainer, not a greenfield rewrite.

---

If you want next, I can:

* Convert this into **GitHub issues**
* Split it into **atomic Copilot tasks**
* Or generate a **pre-commit check** that enforces architectural consistency

