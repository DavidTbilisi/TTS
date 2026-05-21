"""FEAT-7: TTS_ka serve (FastAPI HTTP server)."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from TTS_ka import server


class TestTokenCheck:
    def test_no_expected_token_always_passes(self):
        assert server._check_token(None, None) is True
        assert server._check_token("Bearer x", None) is True

    def test_missing_header_fails(self):
        assert server._check_token(None, "secret") is False

    def test_malformed_header_fails(self):
        assert server._check_token("secret", "secret") is False  # no scheme
        assert server._check_token("Token secret", "secret") is False  # wrong scheme

    def test_correct_bearer_passes(self):
        assert server._check_token("Bearer secret", "secret") is True

    def test_wrong_token_fails(self):
        assert server._check_token("Bearer other", "secret") is False


class TestMissingExtra:
    def test_create_app_missing_fastapi_raises(self):
        with patch.dict(sys.modules, {"fastapi": None}):
            with pytest.raises(server.MissingExtraError) as exc:
                server.create_app()
        assert "TTS_ka[server]" in str(exc.value)

    def test_run_server_missing_uvicorn_raises(self):
        # create_app needs fastapi; run_server then needs uvicorn
        fake_fastapi = MagicMock()
        fake_fastapi.FastAPI = MagicMock(return_value=MagicMock())
        with patch.dict(sys.modules, {
            "fastapi": fake_fastapi,
            "fastapi.responses": MagicMock(
                JSONResponse=MagicMock(),
                StreamingResponse=MagicMock(),
                PlainTextResponse=MagicMock(),
            ),
            "uvicorn": None,
        }):
            with pytest.raises(server.MissingExtraError):
                server.run_server()


class TestCreateApp:
    """Verify create_app() builds an app via the real FastAPI shape (mocked)."""

    def test_registers_expected_routes(self):
        fake_app = MagicMock()
        fake_fastapi = MagicMock()
        fake_fastapi.FastAPI = MagicMock(return_value=fake_app)
        fake_fastapi.HTTPException = type("HTTPException", (Exception,), {})
        fake_fastapi.Header = MagicMock(side_effect=lambda default=None: default)
        fake_fastapi.Request = MagicMock()
        responses_mod = MagicMock()
        with patch.dict(sys.modules, {
            "fastapi": fake_fastapi,
            "fastapi.responses": responses_mod,
        }):
            app = server.create_app()
        # The app must have been created and routes registered via decorators
        assert app is fake_app
        # get() called for "/" and "/voices"
        get_calls = [c.args[0] for c in fake_app.get.call_args_list]
        post_calls = [c.args[0] for c in fake_app.post.call_args_list]
        assert "/" in get_calls
        assert "/voices" in get_calls
        assert "/synthesize" in post_calls


class TestCLIServeSubcommand:
    def test_serve_dispatches_to_run_server(self):
        with patch("sys.argv", ["TTS_ka", "serve", "--port", "9999"]):
            with patch("TTS_ka.server.run_server") as mrun:
                from TTS_ka.main import main
                main()
        mrun.assert_called_once()
        kwargs = mrun.call_args.kwargs
        assert kwargs.get("port") == 9999
        assert kwargs.get("host") == "127.0.0.1"

    def test_serve_default_port(self):
        with patch("sys.argv", ["TTS_ka", "serve"]):
            with patch("TTS_ka.server.run_server") as mrun:
                from TTS_ka.main import main
                main()
        assert mrun.call_args.kwargs.get("port") == 7777

    def test_serve_custom_host(self):
        with patch("sys.argv", ["TTS_ka", "serve", "--host", "0.0.0.0", "--port", "8000"]):
            with patch("TTS_ka.server.run_server") as mrun:
                from TTS_ka.main import main
                main()
        assert mrun.call_args.kwargs.get("host") == "0.0.0.0"

    def test_serve_missing_fastapi_exits_2(self, capsys):
        with patch("sys.argv", ["TTS_ka", "serve"]):
            with patch("TTS_ka.server.run_server",
                       side_effect=server.MissingExtraError()):
                with pytest.raises(SystemExit) as exc:
                    from TTS_ka.main import main
                    main()
        assert exc.value.code == 2
        assert "TTS_ka[server]" in capsys.readouterr().err


class TestSemaphore:
    def test_semaphore_value_matches_max_workers(self):
        # Force a fresh allocation
        globals_in_server = vars(server)
        globals_in_server.pop("_SEM", None)
        sem = server._generation_semaphore()
        # asyncio.Semaphore's internal counter equals MAX_PARALLEL_WORKERS
        from TTS_ka.constants import MAX_PARALLEL_WORKERS
        assert sem._value == MAX_PARALLEL_WORKERS

    def test_semaphore_is_module_singleton(self):
        a = server._generation_semaphore()
        b = server._generation_semaphore()
        assert a is b
