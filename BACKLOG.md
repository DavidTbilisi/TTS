# TTS_ka — Marketability Backlog

Prioritized bugfixes and features written in BDD (Given/When/Then) form with TDD test cases. Severity reflects impact on a paying/marketing audience, not internal correctness alone.

- **P0** — visible defect or missing capability that a casual evaluator will hit in the first 5 minutes
- **P1** — friction or broken-promise issue that hurts trust once a user is past evaluation
- **P2** — polish

---

## Bugs

### BUG-1 (P0): No `--version` flag; version strings out of sync

`pyproject.toml` declares `1.4.2`. `src/TTS_ka/__init__.py:9` declares `1.4.0`. README documents `python -m TTS_ka --version` but no such flag exists in [main.py](src/TTS_ka/main.py) — the user gets a generic argparse error.

**Story** — As a user installing TTS_ka, I want to verify which version I'm running so I can correlate behavior with release notes.

**Scenarios**

```gherkin
Scenario: Show version
  Given the package is installed
  When the user runs `TTS_ka --version`
  Then stdout matches /^TTS_ka \d+\.\d+\.\d+$/
  And exit code is 0

Scenario: Version sources stay in sync
  Given the package version is declared in pyproject.toml
  When `TTS_ka.__version__` is imported
  Then it equals the pyproject.toml [project].version

Scenario: Short form
  When the user runs `TTS_ka -V`
  Then the same version string is printed
```

**TDD**

- `tests/test_main.py::test_version_flag_prints_and_exits_zero` — `subprocess.run([..., "--version"])`, assert exit 0 and regex match on stdout
- `tests/test_version_sync.py::test_dunder_version_matches_pyproject` — read `pyproject.toml`, compare to `TTS_ka.__version__`
- CI guard: a `tox -e check-version` job that fails the build when the two drift

**Acceptance**: `--version` and `-V` print one line and exit 0; `__version__` is read from `pyproject.toml` at build time (e.g. `importlib.metadata.version("TTS_ka")`) rather than duplicated.

---

### BUG-2 (P0): Output path is hardcoded to `data.mp3`

[`main.py:158`](src/TTS_ka/main.py:158) sets `output_path = "data.mp3"`. Two invocations in the same directory overwrite each other; batch processing is impossible without external wrappers.

**Story** — As a user processing multiple documents, I want to choose the output file so I don't clobber previous renderings.

**Scenarios**

```gherkin
Scenario: Custom output path
  When the user runs `TTS_ka "hello" --lang en --output greetings/hello.mp3`
  Then `greetings/hello.mp3` exists and contains a valid MP3 frame header
  And `./data.mp3` is not created

Scenario: Backward-compatible default
  When the user runs `TTS_ka "hello" --lang en` with no --output
  Then `./data.mp3` is created (legacy behavior preserved)

Scenario: Parent directory auto-created
  Given the path `out/2026-05/clip.mp3` does not yet exist
  When the user passes `--output out/2026-05/clip.mp3`
  Then `out/2026-05/` is created
  And the file is written

Scenario: Refuse to overwrite without --force
  Given `out.mp3` already exists
  When the user passes `--output out.mp3`
  Then exit code is non-zero
  And stderr advises to pass `--force` to overwrite

Scenario: Extension inferred
  When the user passes `--output foo` (no extension)
  Then the file is saved as `foo.mp3`
```

**TDD**

- `test_main.py::test_output_flag_writes_to_custom_path` (uses `tmp_path`)
- `test_main.py::test_output_default_is_data_mp3`
- `test_main.py::test_output_creates_parent_directories`
- `test_main.py::test_output_refuses_overwrite_without_force`
- `test_main.py::test_output_force_overwrites_existing`
- `test_main.py::test_output_extension_inferred_when_missing`

**Acceptance**: `-o / --output PATH`, `--force` for overwrite, parent dirs auto-created, default unchanged.

---

### BUG-3 (P0): `--stream` exits with code 1 if VLC is missing

[`ultra_fast.py:189-194`](src/TTS_ka/ultra_fast.py:189) raises `SystemExit(1)` when VLC isn't found. The error message says "Install VLC or run without GUI", but a new user doesn't know what `--no-gui` is, and audio generation aborts entirely instead of falling back. This is the single most damaging first-impression bug.

**Story** — As a first-time user trying `--stream`, I want streaming to gracefully fall back to whatever player I have and to clearly tell me what happened.

**Scenarios**

```gherkin
Scenario: VLC present (happy path)
  Given vlc is on PATH
  When the user runs `TTS_ka "..." --lang en --stream`
  Then VLC GUI launches with the first chunk
  And exit code is 0

Scenario: VLC missing, mpv present
  Given vlc is NOT on PATH but mpv is
  When the user runs `TTS_ka "..." --lang en --stream`
  Then streaming proceeds via mpv (headless)
  And stderr contains "VLC not found; falling back to mpv (no GUI). Install VLC for an interactive player."
  And exit code is 0

Scenario: No supported player at all
  Given no streaming-capable player is available
  When the user runs `TTS_ka "..." --lang en --stream`
  Then audio is still generated to the output file
  And stderr contains "No audio player found; audio saved to <path>. See https://...#players"
  And exit code is 0

Scenario: Explicit player override
  When the user runs `TTS_ka "..." --lang en --stream --player ffplay`
  Then ffplay is used even if VLC is available
```

**TDD**

- `test_ultra_fast.py::test_stream_falls_back_to_mpv_when_vlc_missing` — patch `PlayerDetector.find` returning `"mpv"`, assert no `SystemExit`
- `test_ultra_fast.py::test_stream_no_player_still_generates_file` — patch returning `None`, assert file exists and exit 0
- `test_ultra_fast.py::test_stream_warns_to_stderr_on_fallback`
- `test_ultra_fast.py::test_player_flag_overrides_detection`

**Acceptance**: `--stream` never aborts when audio could still be generated; warnings go to stderr; new `--player NAME` flag.

---

### BUG-4 (P0, security): Shell injection via `os.system` in `play_audio` and `FFmpegMerger`

[`fast_audio.py:310`](src/TTS_ka/fast_audio.py:310): `os.system(f"mpv '{abs_path}' &")`. A filename containing `'` breaks out of the quoted argument. Same risk in [`FFmpegMerger.merge`](src/TTS_ka/fast_audio.py:211) which builds a shell string. This isn't theoretical — users who output to `~/Music/Liam O'Brien.mp3` will break it, and a sufficiently hostile filename can run arbitrary commands.

**Story** — As a user processing arbitrary filenames (downloads, copy-pasted paths), I want the tool to handle special characters safely and not execute shell metacharacters.

**Scenarios**

```gherkin
Scenario: Filename with single quote
  Given an MP3 path "/tmp/Liam O'Brien.mp3"
  When `play_audio` is invoked
  Then the player launches with the literal filename
  And no shell error or unintended command runs

Scenario: Filename with shell metacharacters
  Given output path "Rock & Roll; rm -rf $HOME.mp3"
  When the file is merged and played
  Then the file is processed as a literal filename
  And no part of the filename is interpreted by a shell

Scenario: Static guarantee
  Given the package source tree
  When grepped for `os.system(`
  Then zero matches exist in `src/TTS_ka/**.py`
```

**TDD**

- `test_fast_audio.py::test_play_audio_uses_subprocess_list_form` — patch `subprocess.Popen`, assert call args are a list, `shell=False`
- `test_fast_audio.py::test_play_audio_handles_quote_in_filename` — pass `"a'b.mp3"`, assert no exception, call args correct
- `test_fast_audio.py::test_ffmpeg_merger_uses_argv_not_shell_string`
- `test_security.py::test_no_os_system_calls_in_package` — ast-walk every `.py` under `src/TTS_ka` for `Call(func=Attribute(value=Name("os"), attr="system"))`, assert empty

**Fix direction**: replace every `os.system(...)` with `subprocess.Popen([...], shell=False)` / `subprocess.run([...])`. Use `start_new_session=True` (POSIX) or `creationflags=DETACHED_PROCESS` (Windows) instead of trailing `&`.

---

### BUG-5 (P1, broken promises): README documents env-vars and a config file that don't exist

README sections "Environment Variables" and "Configuration File" describe `TTS_DEFAULT_LANG`, `TTS_DEFAULT_MODE`, `TTS_OUTPUT_DIR`, and `~/.tts_config.json`. None of these are referenced anywhere in `src/`. Users following the README will silently get default behavior.

**Story** — As a power user, I want to set persistent defaults (language, output dir, parallel workers) without retyping flags every invocation.

**Scenarios**

```gherkin
Scenario: Env var sets default language
  Given TTS_DEFAULT_LANG=ru
  When the user runs `TTS_ka "Привет"` with no --lang
  Then the Russian voice is used

Scenario: Explicit flag overrides env var
  Given TTS_DEFAULT_LANG=ru
  When the user runs `TTS_ka "Hello" --lang en`
  Then the English voice is used

Scenario: Config file at ~/.tts_config.json
  Given ~/.tts_config.json contains {"default_lang":"ka","parallel":4}
  When the user runs `TTS_ka "..."`
  Then Georgian voice is used with 4 workers

Scenario: Precedence (CLI > env > config > built-in)
  Given config.json sets lang=ka
  And env sets TTS_DEFAULT_LANG=ru
  And CLI passes --lang en
  When the command runs
  Then English is chosen

Scenario: Unknown config keys
  Given the config file contains an unknown key "spelm"
  When the command runs
  Then stderr warns about the unknown key
  And the command does not abort
```

**TDD**

- `test_config.py::test_env_var_overrides_builtin_default`
- `test_config.py::test_cli_flag_overrides_env_var`
- `test_config.py::test_config_file_loaded_from_xdg_config_home_then_home_dotfile`
- `test_config.py::test_precedence_cli_env_config_default`
- `test_config.py::test_unknown_config_keys_warn_but_dont_crash`
- `test_config.py::test_malformed_json_warns_and_uses_defaults`

**Acceptance**: implement the documented config layer, including XDG path support (`$XDG_CONFIG_HOME/TTS_ka/config.json`) — or delete the README sections. Recommend implementing; pairs with [FEAT-1](#feat-1).

---

### BUG-6 (P1, correctness regression risk): No guard against `_DEFAULT_FILTERS` mutation

[`not_reading.py:90`](src/TTS_ka/not_reading.py:90) is currently safe because of the `list(self._DEFAULT_FILTERS)` copy. There is no test locking that invariant. A future refactor that drops the copy will silently corrupt every pipeline instance.

**Story** — As a maintainer, I want a regression test that fails immediately if filter lists are accidentally shared across instances.

**Scenarios**

```gherkin
Scenario: Filter list is per-instance
  Given two pipelines created with the default constructor
  When one of them appends a filter to its internal list
  Then the other pipeline's filter list is unchanged

Scenario: Class default unmodified
  Given a pipeline mutates its instance filter list
  When a third pipeline is constructed
  Then it still has exactly the original default filters
```

**TDD**

- `test_not_readable.py::test_default_filters_are_per_instance_copy`
- `test_not_readable.py::test_class_default_filters_unmodified_after_instance_mutation`

---

## Features

<a id="feat-1"></a>
### FEAT-1 (P0): Voice catalog + `--voice`, `--list-voices`, `--preview-voice`

**Why it sells**: One voice per language is a deal-breaker for audiobook creators, language learners (male vs. female), and accessibility users. Edge-TTS exposes ~400 voices; surfacing them costs almost nothing.

**Story** — As a user, I want to pick a specific voice (or list/preview voices) instead of being locked to one per language.

**Scenarios**

```gherkin
Scenario: List voices
  When the user runs `TTS_ka --list-voices`
  Then stdout is a table of (language, voice_id, gender, locale, short_description)
  And exit code is 0

Scenario: Filter list by language
  When the user runs `TTS_ka --list-voices --lang en`
  Then only English voices are listed

Scenario: Preview a voice
  When the user runs `TTS_ka --preview-voice en-US-JennyNeural`
  Then a short fixed sample plays
  And no `data.mp3` is left on disk

Scenario: Use a specific voice
  When the user runs `TTS_ka "hello" --voice en-US-JennyNeural`
  Then that voice is used
  And --lang is inferred from the voice locale

Scenario: Voice/lang mismatch
  When the user passes `--lang en --voice ka-GE-EkaNeural`
  Then exit code is non-zero
  And stderr explains the mismatch
```

**TDD**

- `test_voices.py::test_list_voices_returns_known_subset`
- `test_voices.py::test_list_voices_filtered_by_lang`
- `test_voices.py::test_preview_voice_writes_and_deletes_temp_file`
- `test_voices.py::test_voice_flag_used_in_ssml`
- `test_voices.py::test_voice_lang_mismatch_errors_with_clear_message`
- `test_voices.py::test_voice_catalog_includes_existing_three_defaults`

**Implementation note**: `VOICE_MAP` in [constants.py](src/TTS_ka/constants.py) becomes a richer `VOICES` registry (id, lang, gender, display_name). Populate from `edge-tts --list-voices` at build time and cache in package data.

---

### FEAT-2 (P0): Speech rate / pitch / volume via SSML prosody

**Why it sells**: Universally expected. Language learners need slower playback; re-listeners want faster. Audiobook tone needs pitch/volume tweaks. Tiny implementation effort.

**Story** — As a user, I want to control speech rate, pitch, and volume per invocation.

**Scenarios**

```gherkin
Scenario: Faster playback
  When the user runs `TTS_ka "hello world" --rate +30%`
  Then the audio duration is 20–30% shorter than the default rendering

Scenario: Lower pitch
  When the user runs `TTS_ka "hello" --pitch -20Hz`
  Then the audio has a measurably lower fundamental frequency than the default

Scenario: Volume boost
  When the user passes `--volume +10%`
  Then the RMS amplitude is higher than the default

Scenario: Invalid value rejected before any HTTP call
  When the user passes `--rate banana`
  Then exit code is non-zero
  And no HTTP request is sent

Scenario: Extreme value clamped with warning
  When the user passes `--rate +500%`
  Then the value is clamped to a documented safe max
  And stderr warns about the clamp
```

**TDD**

- `test_prosody.py::test_rate_arg_appears_in_generated_ssml`
- `test_prosody.py::test_pitch_arg_appears_in_generated_ssml`
- `test_prosody.py::test_volume_arg_appears_in_generated_ssml`
- `test_prosody.py::test_rate_validation_rejects_garbage`
- `test_prosody.py::test_extreme_values_clamped_with_warning`
- `test_prosody.py::test_no_prosody_args_yields_unwrapped_ssml` (no perf regression for default users)
- Integration: render a fixed phrase at `--rate +0%` and `--rate +50%`; assert second file duration is >25% shorter (use `mutagen` or `soundfile` for duration).

---

### FEAT-3 (P0): PDF, EPUB, DOCX, HTML, Markdown input

**Why it sells**: Massively widens the audience — researchers, students, audiobook hobbyists. Currently they have to manually extract text first, which is enough friction to push them to a competitor.

**Story** — As a user, I want to point TTS_ka at a PDF, EPUB, DOCX, HTML, or Markdown file and have it extract text and read it.

**Scenarios**

```gherkin
Scenario: PDF input
  Given a file "paper.pdf"
  When the user runs `TTS_ka paper.pdf --lang en`
  Then text is extracted preserving paragraph breaks
  And audio is generated

Scenario: EPUB with chapters
  Given an EPUB "book.epub" with 12 chapters
  When the user runs `TTS_ka book.epub --lang en --output book.mp3`
  Then a single MP3 is generated
  And chapter markers are embedded (see FEAT-5)

Scenario: Markdown stripping
  Given a README.md with code fences and links
  When run as input
  Then code blocks and URLs are sanitized BEFORE TTS (existing not_reading.py handles this)
  And no markdown punctuation (`#`, `*`, `>`) is audible

Scenario: Unknown extension
  Given a file with an unknown extension
  When passed as input
  Then it falls back to plain-text reading

Scenario: Optional extras not installed
  Given pypdf is not installed
  When the user passes a PDF
  Then exit code is non-zero
  And stderr says `pip install TTS_ka[readers]`
```

**TDD**

- `test_readers.py::test_pdf_reader_extracts_known_fixture`
- `test_readers.py::test_epub_reader_yields_chapter_tuples`
- `test_readers.py::test_docx_reader_extracts_paragraphs`
- `test_readers.py::test_html_reader_strips_tags_and_scripts`
- `test_readers.py::test_markdown_reader_strips_syntax`
- `test_readers.py::test_unknown_extension_falls_back_to_plain`
- `test_readers.py::test_missing_optional_dep_yields_actionable_error`

**Architecture**: introduce `src/TTS_ka/readers/` with a `TextReader` protocol; dispatch by extension. Make dependencies (`pypdf`, `ebooklib`, `python-docx`, `beautifulsoup4`) optional extras: `pip install TTS_ka[readers]`.

---

### FEAT-4 (P1): Stdin input + JSON progress output

**Why it sells**: Unlocks Unix-style pipelines and integration with other tools (RSS readers, Slack bots, CI). JSON mode makes the tool embeddable.

**Story** — As a developer integrating TTS_ka, I want to pipe text in and get machine-readable progress out.

**Scenarios**

```gherkin
Scenario: Auto-detect piped stdin
  Given stdin is not a TTY and contains "Hello world"
  When the user runs `cat file.txt | TTS_ka --lang en`
  Then audio is generated from the piped text

Scenario: Explicit dash
  When the user runs `TTS_ka - --lang en` with text on stdin
  Then audio is generated from stdin

Scenario: JSON progress
  When the user runs `TTS_ka "long text" --lang en --json`
  Then every stdout line is a valid JSON object
  And events include
    {"event":"start","chunks":N}
    {"event":"chunk_done","index":i,"elapsed":s}
    {"event":"done","output":"data.mp3","seconds":s}
  And no decorative emoji output appears

Scenario: JSON and --quiet compose
  When the user passes both `--json` and `--quiet`
  Then only the final {"event":"done"} line is printed
```

**TDD**

- `test_main.py::test_stdin_input_when_no_text_arg_and_not_tty`
- `test_main.py::test_explicit_dash_reads_stdin`
- `test_main.py::test_text_arg_takes_precedence_over_stdin`
- `test_json_output.py::test_each_progress_line_is_valid_json`
- `test_json_output.py::test_json_mode_suppresses_emoji_lines`
- `test_json_output.py::test_json_done_event_has_output_path_and_duration`
- `test_json_output.py::test_json_error_event_on_failure`

---

### FEAT-5 (P1): ID3 tags & audiobook chapter markers

**Why it sells**: Distinguishes TTS_ka from quick-and-dirty scripts. Lets users generate audiobooks playable in Audible-style apps, podcast clients, and car stereos with proper title/author/cover/chapter UI.

**Story** — As an audiobook creator, I want generated MP3s to carry title/author/cover/chapter metadata so they look right in any player.

**Scenarios**

```gherkin
Scenario: Title and author
  When the user runs `TTS_ka book.epub --title "War & Peace" --author "Tolstoy" --output wp.mp3`
  Then the MP3 ID3v2 tag contains TIT2="War & Peace" and TPE1="Tolstoy"

Scenario: Embed cover art
  When the user passes `--cover cover.jpg`
  Then the MP3 contains an APIC frame with the JPEG bytes

Scenario: Chapter markers from EPUB
  Given an EPUB with 5 chapters
  When generated with defaults
  Then the MP3 has 5 ID3v2 CHAP frames
  And opening in a chapter-aware player shows the EPUB's chapter titles

Scenario: No flags, no surprises
  When the user passes none of the metadata flags
  Then the file has no ID3 tags
```

**TDD**

- `test_metadata.py::test_id3_title_author_album_written` (read back with `mutagen`)
- `test_metadata.py::test_cover_art_embedded_as_apic`
- `test_metadata.py::test_chapter_frames_match_input_chapter_count`
- `test_metadata.py::test_chapter_titles_propagate_from_epub`
- `test_metadata.py::test_no_metadata_flags_leaves_file_untagged`

**Dep**: `mutagen` (mature, BSD, no native deps). Should be a hard dep — small enough to justify.

---

### FEAT-6 (P1): Subtitle export (SRT / VTT)

**Why it sells**: Accessibility + content creator win (YouTube voiceovers, video dubbing). Few free TTS CLIs offer this neatly.

**Story** — As a content creator, I want a synced subtitle file alongside the audio so I can use TTS output for video voiceovers.

**Scenarios**

```gherkin
Scenario: Export SRT
  When the user runs `TTS_ka script.txt --lang en --output v1.mp3 --srt`
  Then `v1.srt` is created next to `v1.mp3`
  And each subtitle entry's timing matches a sentence/word boundary in the source

Scenario: Export VTT
  When the user passes `--vtt` instead of `--srt`
  Then `v1.vtt` is created with a WebVTT header

Scenario: Combined --srt --vtt
  When both flags are passed
  Then both files are produced
```

**TDD**

- `test_subtitles.py::test_srt_file_created_alongside_mp3`
- `test_subtitles.py::test_srt_timings_strictly_increasing`
- `test_subtitles.py::test_srt_text_concatenation_equals_input`
- `test_subtitles.py::test_vtt_header_present`
- `test_subtitles.py::test_word_boundary_events_drive_timing` (mock edge-tts `WordBoundary` stream)

**Implementation note**: edge-tts emits `WordBoundary` events; use them to drive timing rather than guessing from chunk durations.

---

### FEAT-7 (P1): REST/HTTP server mode (`TTS_ka serve`)

**Why it sells**: Cheapest path from "CLI tool" to "product". Embeds TTS_ka in web apps, browser extensions, language-learning sites, Home Assistant.

**Story** — As a developer, I want to run TTS_ka as a local HTTP service so my app can POST text and get back audio.

**Scenarios**

```gherkin
Scenario: Start the server
  When the user runs `TTS_ka serve --port 7777`
  Then GET / returns 200 with a small JSON OK message
  And GET /voices returns a JSON list of voices

Scenario: Synthesize via POST
  Given the server is running
  When the client POSTs /synthesize {"text":"hello","lang":"en"}
  Then the response Content-Type is audio/mpeg
  And the response body streams the bytes as they generate (chunked transfer)

Scenario: Token auth
  Given env var TTS_API_TOKEN=secret
  When a client sends a request without Authorization
  Then HTTP 401
  When a client sends Authorization: Bearer secret
  Then HTTP 200

Scenario: Concurrency cap respected
  Given MAX_PARALLEL_WORKERS=4
  When 10 simultaneous /synthesize requests arrive
  Then at most 4 generations run concurrently
  And the remaining 6 queue without timing out

Scenario: Invalid lang
  When the client posts {"text":"x","lang":"zz"}
  Then HTTP 400 with a JSON error body
```

**TDD**

- `test_server.py::test_get_voices_returns_known_voices`
- `test_server.py::test_post_synthesize_returns_audio_mpeg`
- `test_server.py::test_post_synthesize_streams_chunked`
- `test_server.py::test_missing_token_returns_401_when_env_set`
- `test_server.py::test_invalid_lang_returns_400_json`
- `test_server.py::test_concurrent_load_respects_worker_cap`
- `test_server.py::test_request_with_prosody_flags_in_body`

**Stack**: FastAPI + uvicorn (async-native; matches existing asyncio code). Optional extra: `pip install TTS_ka[server]`.

---

### FEAT-8 (P2): Shell completions + man page

**Why it sells**: Cheap polish that signals "production tool". Discoverability matters once the flag surface grows past 5 options.

**Story** — As a CLI user, I want tab-completion for flags, languages, and voice names in bash/zsh/fish.

**Scenarios**

```gherkin
Scenario: Print completion script
  When the user runs `TTS_ka --print-completion bash`
  Then stdout contains a syntactically valid bash completion script
  And exit code is 0

Scenario: Tab-complete --lang
  Given completions are installed
  When the user types `TTS_ka "x" --lang <TAB>`
  Then candidates "en ka ru" are offered

Scenario: Tab-complete --voice
  Given completions are installed
  When the user types `TTS_ka "x" --voice en-<TAB>`
  Then candidates list all English voice ids

Scenario: Man page
  Given the package is installed
  When the user runs `man TTS_ka` on Unix
  Then the manpage renders
```

**TDD**

- `test_completions.py::test_bash_completion_script_passes_bash_n` — `subprocess.run(["bash", "-n", "-c", script])`
- `test_completions.py::test_zsh_completion_uses_compdef`
- `test_completions.py::test_fish_completion_uses_complete_directive`
- `test_completions.py::test_voice_completion_lists_known_voice_ids`

**Stack**: `shtab` layered on top of existing `argparse` — minimal disruption. Generate manpage via `argparse-manpage`.

---

## Suggested execution order

| Sprint | Items | Theme |
|--------|-------|-------|
| 1 (1 wk) | BUG-1, BUG-2, BUG-4, BUG-6 | No broken promises; no security smell |
| 2 (1–2 wk) | BUG-3, BUG-5, FEAT-2, FEAT-4 | UX polish + scriptability |
| 3 (2–3 wk) | FEAT-1, FEAT-3, FEAT-8 | "v2.0" launch posture |
| 4 (2–3 wk) | FEAT-5, FEAT-6, FEAT-7 | Audiobook & integration story complete |

## Cross-cutting acceptance gates

- Coverage stays ≥ 80% (per [pytest.ini](pytest.ini))
- `black`, `flake8`, `mypy` all clean on `src/`
- No `os.system(` anywhere under `src/TTS_ka/` (enforced by [BUG-4](#bug-4-p0-security-shell-injection-via-ossystem-in-play_audio-and-ffmpegmerger))
- Every new public function has a docstring matching the codebase's terse style
- Every new dep is justified in the PR description (size, license, native deps)
