"""End-to-end MCP test: spawn the server as a subprocess and exercise the protocol.

Marked ``slow`` so fast unit runs (``pytest -m "not slow"``) skip the subprocess
boot. Only calls tools whose code paths do NOT trigger audio synthesis — the
test process has no network/edge-tts access, and a hanging synth would block
``stream_close`` for the full edge-tts timeout. Each test is wrapped in an
``asyncio.wait_for`` so any regression that re-introduces a synth hang fails
in 15 s rather than 16 min.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="mcp extra not installed")


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = str(REPO_ROOT / "src")
HARD_TIMEOUT = 15.0  # seconds — any test exceeding this is presumed hung


@pytest.fixture
def server_env():
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = SRC + (os.pathsep + existing if existing else "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


async def _exercise_lifecycle(server_env):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "TTS_ka.mcp_server"],
        env=server_env,
        cwd=str(REPO_ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {
                "speak",
                "stream_open",
                "stream_append",
                "stream_close",
                "stop",
                "list_voices",
                "session_status",
                "list_sessions",
            }.issubset(names), names

            r = await session.call_tool("list_voices", {"lang": "en"})
            voices = _unwrap(r)
            assert isinstance(voices, list) and voices
            assert all(v["lang"] == "en" for v in voices)

            r = await session.call_tool("stream_open", {"lang": "en"})
            sid = _unwrap(r)
            assert isinstance(sid, str) and sid

            r = await session.call_tool("session_status", {"session_id": sid})
            snap = _unwrap(r)
            assert snap["session_id"] == sid
            assert snap["lang"] == "en"
            assert snap["closed"] is False
            assert snap["total_sentences"] == 0

            r = await session.call_tool("list_sessions", {})
            listing = _unwrap(r)
            assert any(s["session_id"] == sid for s in listing)

            # Close on empty buffer — no drain → no synth → no network call.
            r = await session.call_tool("stream_close", {"session_id": sid})
            assert "closed" in _unwrap(r)


@pytest.mark.slow
@pytest.mark.asyncio
async def test_e2e_lifecycle(server_env):
    await asyncio.wait_for(_exercise_lifecycle(server_env), timeout=HARD_TIMEOUT)


async def _exercise_unknown_session(server_env):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "TTS_ka.mcp_server"],
        env=server_env,
        cwd=str(REPO_ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            r = await session.call_tool(
                "stream_append", {"session_id": "bogus", "text": "x"}
            )
            assert "unknown session_id" in _unwrap(r)
            r = await session.call_tool(
                "session_status", {"session_id": "bogus"}
            )
            snap = _unwrap(r)
            assert "error" in snap


@pytest.mark.slow
@pytest.mark.asyncio
async def test_e2e_unknown_session_errors(server_env):
    await asyncio.wait_for(_exercise_unknown_session(server_env), timeout=HARD_TIMEOUT)


def _ttska_tmp_dirs():
    import glob
    import tempfile
    return set(glob.glob(os.path.join(tempfile.gettempdir(), "ttska-mcp-*")))


async def _exercise_unclosed_session(server_env):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "TTS_ka.mcp_server"],
        env=server_env,
        cwd=str(REPO_ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # Never closed: the server must still remove its temp dir on exit.
            r = await session.call_tool("stream_open", {"lang": "en"})
            assert _unwrap(r)


@pytest.mark.slow
@pytest.mark.asyncio
async def test_e2e_exit_removes_temp_dirs(server_env):
    before = _ttska_tmp_dirs()
    await asyncio.wait_for(_exercise_unclosed_session(server_env), timeout=HARD_TIMEOUT)
    assert _ttska_tmp_dirs() - before == set()


# Server whose extra `noisy` tool prints from Python and from a child process.
_NOISY_SERVER = """
import subprocess, sys
import TTS_ka.mcp_server as m

_build = m.build_server

def build_server(**kw):
    server = _build(**kw)

    @server.tool()
    def noisy() -> str:
        print("PY-PRINT")
        subprocess.run([sys.executable, "-c", "print('CHILD-PRINT')"])
        return "ok"

    return server

m.build_server = build_server
m.main()
"""


async def _exercise_stray_output(server_env, errlog):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", _NOISY_SERVER],
        env=server_env,
        cwd=str(REPO_ROOT),
    )
    async with stdio_client(params, errlog=errlog) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            r = await session.call_tool("noisy", {})
            assert _unwrap(r) == "ok"


@pytest.mark.slow
@pytest.mark.asyncio
async def test_e2e_stray_output_goes_to_stderr(server_env, tmp_path):
    """print() and child output must land on stderr, never on the JSON-RPC pipe.

    Covers the shutdown case too: a print still in sys.stdout's buffer when the
    transport restores fd 1 would otherwise be flushed onto the wire.
    """
    with open(tmp_path / "stderr.txt", "w+", encoding="utf-8") as errlog:
        await asyncio.wait_for(
            _exercise_stray_output(server_env, errlog), timeout=HARD_TIMEOUT
        )
        errlog.seek(0)
        err = errlog.read()
    assert "PY-PRINT" in err
    assert "CHILD-PRINT" in err
    assert "Invalid JSON" not in err


def _unwrap(call_result):
    sc = call_result.structured_content
    if isinstance(sc, dict) and list(sc.keys()) == ["result"]:
        return sc["result"]
    return sc
