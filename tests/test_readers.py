"""FEAT-3: PDF/EPUB/DOCX/HTML/Markdown readers."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from TTS_ka.readers import read_file, READERS, MissingExtraError


class TestDispatch:
    def test_unknown_extension_uses_plain(self, tmp_path):
        f = tmp_path / "nonsense.xyz"
        f.write_text("hello", encoding="utf-8")
        assert read_file(str(f)) == "hello"

    def test_txt_uses_plain_reader(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("just text", encoding="utf-8")
        assert read_file(str(f)) == "just text"

    def test_extension_case_insensitive(self, tmp_path):
        f = tmp_path / "a.TXT"
        f.write_text("upper", encoding="utf-8")
        assert read_file(str(f)) == "upper"

    def test_md_dispatch_in_registry(self):
        assert ".md" in READERS
        assert ".markdown" in READERS


class TestMarkdownReader:
    def test_strips_code_fences(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("Hello\n\n```python\nprint('x')\n```\n\nWorld", encoding="utf-8")
        out = read_file(str(f))
        assert "print" not in out
        assert "Hello" in out and "World" in out

    def test_strips_headings(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nBody text.", encoding="utf-8")
        out = read_file(str(f))
        assert "#" not in out
        assert "Title" in out
        assert "Body" in out

    def test_keeps_link_text_drops_url(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("Read [Anthropic](https://anthropic.com) docs.", encoding="utf-8")
        out = read_file(str(f))
        assert "Anthropic" in out
        assert "https" not in out

    def test_strips_bullets_and_blockquotes(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("- item one\n- item two\n\n> quoted line", encoding="utf-8")
        out = read_file(str(f))
        assert ">" not in out
        # Bullet markers must be gone but the words remain
        assert "item one" in out and "quoted line" in out


class TestHTMLReader:
    def test_strips_tags_and_scripts(self, tmp_path):
        f = tmp_path / "p.html"
        html = (
            "<html><head><script>alert(1)</script><style>.x{}</style></head>"
            "<body><p>Hello <b>world</b></p></body></html>"
        )
        f.write_text(html, encoding="utf-8")
        out = read_file(str(f))
        assert "alert" not in out
        assert ".x" not in out
        assert "Hello" in out and "world" in out
        assert "<" not in out and ">" not in out


class TestOptionalDeps:
    def test_pdf_missing_dep_actionable_error(self, tmp_path):
        f = tmp_path / "x.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        # Force pypdf import to fail by removing it from sys.modules and
        # blocking the import.
        with patch.dict(sys.modules, {"pypdf": None}):
            with pytest.raises(MissingExtraError) as exc:
                read_file(str(f))
        msg = str(exc.value)
        assert "PDF" in msg
        assert "pip install TTS_ka[readers]" in msg

    def test_epub_missing_dep_actionable_error(self, tmp_path):
        f = tmp_path / "x.epub"
        f.write_bytes(b"PK\x03\x04")
        with patch.dict(sys.modules, {"ebooklib": None}):
            with pytest.raises(MissingExtraError) as exc:
                read_file(str(f))
        assert "EPUB" in str(exc.value)

    def test_docx_missing_dep_actionable_error(self, tmp_path):
        f = tmp_path / "x.docx"
        f.write_bytes(b"PK\x03\x04")
        with patch.dict(sys.modules, {"docx": None}):
            with pytest.raises(MissingExtraError) as exc:
                read_file(str(f))
        assert "DOCX" in str(exc.value)


class TestPDFWithMock:
    def test_pdf_extracts_text_from_pages(self, tmp_path):
        f = tmp_path / "x.pdf"
        f.write_bytes(b"%PDF-1.4\n")

        fake_page1 = MagicMock()
        fake_page1.extract_text.return_value = "Page one content"
        fake_page2 = MagicMock()
        fake_page2.extract_text.return_value = "Page two content"
        fake_reader = MagicMock()
        fake_reader.pages = [fake_page1, fake_page2]

        fake_pypdf = MagicMock()
        fake_pypdf.PdfReader = MagicMock(return_value=fake_reader)
        with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
            result = read_file(str(f))
        assert "Page one content" in result
        assert "Page two content" in result


class TestMainIntegration:
    def test_main_reads_markdown_file(self, tmp_path):
        from unittest.mock import AsyncMock
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nHello world.", encoding="utf-8")
        with patch("sys.argv", ["TTS_ka", str(f), "--lang", "en", "--no-play"]):
            with patch("TTS_ka.main.fast_generate_audio",
                       new=AsyncMock(return_value=True)) as mfa, \
                 patch("TTS_ka.main.cleanup_http", new=AsyncMock()), \
                 patch("TTS_ka.main.get_optimal_settings",
                       return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
                from TTS_ka.main import main
                main()
        # The text passed to fast_generate_audio should not include the '#' marker.
        text_passed = mfa.call_args.args[0]
        assert "#" not in text_passed
        assert "Title" in text_passed

    def test_main_pdf_missing_dep_exits_2(self, tmp_path, capsys):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        with patch("sys.argv", ["TTS_ka", str(f), "--lang", "en", "--no-play"]):
            with patch.dict(sys.modules, {"pypdf": None}):
                with pytest.raises(SystemExit) as exc:
                    from TTS_ka.main import main
                    main()
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "TTS_ka[readers]" in err
