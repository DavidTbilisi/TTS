# TTS_ka Architecture & Workflows

This document contains Mermaid diagrams that map the repository structure, show how modules connect, and illustrate the primary workflows (direct generation, smart chunked generation, streaming playback, CLI and programmatic (facade) usage).

Open the diagrams on GitHub, in VS Code with Mermaid preview, or paste the Mermaid code into https://mermaid.live to render.

---

## 1) High-level module map (package structure)

```mermaid
flowchart LR
  subgraph Package [TTS_ka Package]
    A(__main__.py / main.py)
    B(cli.py)
    C(facades.py)
    CORE(core.py)
    D(audio.py)
    E(fast_audio.py)
    F(ultra_fast.py)
    G(chunking.py)
    H(chunker.py)
    I(streaming_player.py)
    J(not_reading.py)
    K(simple_help.py)
    L(rich_progress.py)
    M(parallel.py)
  end

  %% primary user entrypoints
  User[(User / CLI / Python API)] --> A
  User --> B
  User --> C

  %% facades route through core
  C --> CORE
  A --> CORE
  B --> CORE

  %% core delegates to generation internals
  CORE --> E
  CORE --> F
  CORE --> D
  CORE --> I

  %% generation internals
  F --> E
  F --> I
  F --> G
  E --> D
  E --> J

  %% helpers
  G --> J
  L --> F
  M --> F

  style Package fill:#f6f8fa,stroke:#333,stroke-width:1px
``` 

Short notes:
- `facades.py` exposes simple synchronous APIs (generate, generate_bytes, stream, merge, play).
- `main.py` and `cli.py` are CLI entrypoints that call `fast_audio` or `ultra_fast` depending on input size and flags.
- `fast_audio.py` implements low-latency direct HTTP-based generation and fallback to `edge-tts`.
- `ultra_fast.py` contains chunking/parallel orchestration and uses `streaming_player.py` for streaming playback.
- `audio.py` contains basic audio utilities and play/merge helpers; `not_reading.py` sanitizes text.

---

## 2) Workflow: Direct (Ultra-fast) generation (short text)

```mermaid
flowchart TD
  U[User: small text] -->|call CLI or facades.generate| Entrypoint["main / cli / facades"]
  Entrypoint -->|direct path| FastGen[fast_audio.fast_generate_audio]
  FastGen -->|writes| Output[data.mp3]
  Entrypoint -->|if --play| Play[audio.play_audio]
  Fallback["fast_audio.fallback_generate_audio<br/>(edge-tts)"]
  FastGen -->|on failure| Fallback
  Fallback --> Output

  subgraph notes
    note1["When text is short (&lt;~200 words) the direct (fast) path is used — very low latency."]
  end

  style notes fill:#fffbe6,stroke:#f1c40f
```

Key points:
- Fast HTTP streaming to file via `httpx` is attempted.
- If the direct API fails, `edge-tts` fallback is used.
- `facades.generate` wraps this as a synchronous operation (calls `asyncio.run`).

---

## 3) Workflow: Smart chunked generation (long text)

```mermaid
flowchart TD
  U[User: long text / file] --> Entrypoint["main / cli / facades"]
  Entrypoint -->|chunking| Chunker[chunking.split_text_into_chunks]
  Chunker -->|chunks list| Orchestrator[ultra_fast.smart_generate_long_text]
  Orchestrator -->|parallel tasks| Parallel[ultra_fast.ultra_fast_parallel_generation]
  Parallel -->|calls| FastGen[fast_audio.fast_generate_audio]
  FastGen --> PartFiles[.part_*.mp3]
  Parallel -->|collect| Parts[parts list]
  Orchestrator --> Merge[fast_merge_audio_files]
  Merge --> Output[data.mp3]
  Orchestrator -->|cleanup| Cleanup[ultra_fast.ultra_fast_cleanup_parts]
  Entrypoint -->|optionally --play| PlayAudio[play_audio]
  PlayAudio --> Output

  subgraph notes
    note1["Chunk size and parallelism are auto-optimized by get_optimal_settings()."]
  end
  style notes fill:#f6ffed,stroke:#27ae60
```

Key points:
- For long input, text is split into chunks and processed in parallel.
- The `ultra_fast` orchestrator handles merging and cleanup.
- `rich_progress` may display progress during parallel generation.

---

## 4) Workflow: Streaming playback (play while generating)

```mermaid
flowchart LR
  U[User: long text + --stream] --> Entrypoint["main / cli / facades"]
  Entrypoint --> SmartGen["smart_generate_long_text (stream enabled)"]
  SmartGen --> StreamingPlayer["StreamingAudioPlayer (started)"]
  StreamingPlayer --> UltraParallel[ultra_fast_parallel_generation with streaming_player]
  UltraParallel --> FastGen[fast_audio.fast_generate_audio]
  FastGen -->|part ready| StreamingPlayerAdd[add_chunk]
  StreamingPlayerAdd --> StreamingPlayer
  StreamingPlayer -->|play first chunk immediately| LocalPlayer[VLC/mpv/ffplay/os player]
  WhenDone[When generation finishes] --> Finish[finish_generation]
  Finish --> Merge[fast_merge_audio_files]
  Merge --> Output[data.mp3]

  subgraph notes
    note1["StreamingPlayer takes the first chunk as the playable file and coordinates seamless playback with a playlist/merge when done."]
  end
  style notes fill:#eef7ff,stroke:#3498db
```

Key points:
- `StreamingAudioPlayer` queues chunks and plays them as they become available.
- On Windows the first chunk often becomes the main output; other platforms can create playlists.

---

## 5) Workflow: CLI vs Programmatic (facade) usage

```mermaid
flowchart LR
  UserCLI["User (shell)"] --> CLI["python -m TTS_ka"]
  CLI --> CLI_files["cli.py, main.py"]
  UserLib["User (Python program)"] --> Facade["from TTS_ka import generate, generate_bytes"]

  CLI --> core_flow[main orchestration]
  Facade --> core_flow

  core_flow --> choose_path{size/flags}
  choose_path --> direct[fast_audio]
  choose_path --> chunked[ultra_fast]
  choose_path --> stream[ultra_fast + streaming_player]
```

Notes:
- The facades present a simpler API for programmatic use and tests; they call the same internals as the CLI.
- CLI flow includes CLI parsing, help, and file/clipboard handling.

---

## 6) Developer/workflow diagram (running tests, lint, CI)

```mermaid
flowchart LR
  Dev[Developer machine] --> Setup["Create venv<br/>pip install -r requirements-test.txt"]
  Setup --> PreCommit["pre-commit hooks<br/>(Black, isort, flake8, mypy)"]
  Dev --> Test[pytest]
  Dev --> Lint["bash lint.sh<br/>black / isort / flake8 / mypy"]

  GitHub[Repository] --> CI[".github/workflows/ci.yml"]
  CI --> Test
  CI --> TypeCheck[mypy]

  style Test fill:#fff0f0,stroke:#e74c3c
```

---

## Legend
- Boxes represent files or components.
- Arrows indicate call/usage or data flow.
- Colors are for visual grouping (notes highlighted boxes).

---

## How to view
- Paste any Mermaid block (between ```mermaid and ```) into https://mermaid.live/ to render.
- In VS Code, install "Markdown Preview Mermaid Support" or use built-in Mermaid rendering to preview `docs/architecture.md`.

---

If you want, I can:
- Add PNG/SVG exports of these diagrams in `docs/` so they render on platforms without Mermaid support.
- Produce a one-page printable PDF architecture sheet.
- Generate a simplified ASCII diagram for reading in terminals.

Which would you prefer next?
