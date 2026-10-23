"""FEAT-3: PDF/EPUB/DOCX/HTML/Markdown readers."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from TTS_ka.readers import read_file, READERS, MissingExtraError
from TTS_ka.readers import pdf as pdf_reader


@pytest.fixture(autouse=True)
def _no_pdftotext(monkeypatch):
    """Use the pypdf path by default, whether or not poppler is installed here."""
    monkeypatch.setattr(pdf_reader, "_pdftotext_exe", lambda: None)


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


def _fake_pdf(texts):
    """A fake ``pypdf`` module whose reader has one MagicMock page per text."""
    pages = []
    for text in texts:
        page = MagicMock()
        page.extract_text.return_value = text
        pages.append(page)
    fake_pypdf = MagicMock()
    fake_pypdf.PdfReader = MagicMock(return_value=MagicMock(pages=pages))
    return fake_pypdf, pages


class TestPageSpec:
    @pytest.mark.parametrize("spec, expected", [
        ("3", [2]),
        ("2-4", [1, 2, 3]),
        (" 2 - 4 ", [1, 2, 3]),
        ("8-", [7, 8, 9]),
        ("-2", [0, 1]),
        ("1-3,7,9-", [0, 1, 2, 6, 8, 9]),
        ("5,1-2", [4, 0, 1]),           # order as given
        ("1-3,2-4", [0, 1, 2, 3]),      # each page once
        ("10", [9]),
    ])
    def test_valid(self, spec, expected):
        from TTS_ka.readers.pdf import parse_page_spec
        assert parse_page_spec(spec, 10) == expected

    @pytest.mark.parametrize("spec, message", [
        ("", "empty"),
        (" , ", "empty"),
        ("abc", "invalid page range"),
        ("1-x", "invalid page range"),
        ("0", "invalid page range"),
        ("5-3", "invalid page range"),
        ("11", "past the end"),
        ("8-12", "past the end"),
    ])
    def test_invalid(self, spec, message):
        from TTS_ka.readers import PageRangeError
        from TTS_ka.readers.pdf import parse_page_spec
        with pytest.raises(PageRangeError, match=message):
            parse_page_spec(spec, 10)


class TestPdfPages:
    def test_extracts_only_selected_pages_in_order(self, tmp_path):
        f = tmp_path / "book.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        fake_pypdf, pages = _fake_pdf([f"page {n}" for n in range(1, 6)])
        with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
            result = read_file(str(f), pages="4,2")
        assert result == "page 4\n\npage 2"
        assert [p.extract_text.called for p in pages] == [False, True, False, True, False]

    def test_out_of_range_raises(self, tmp_path):
        from TTS_ka.readers import PageRangeError
        f = tmp_path / "book.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        fake_pypdf, _ = _fake_pdf(["a", "b"])
        with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
            with pytest.raises(PageRangeError, match="has 2 pages"):
                read_file(str(f), pages="3")

    def test_non_pdf_raises(self, tmp_path):
        from TTS_ka.readers import PageRangeError
        f = tmp_path / "notes.txt"
        f.write_text("hello", encoding="utf-8")
        with pytest.raises(PageRangeError, match="only works with PDF"):
            read_file(str(f), pages="1")


class TestMainPages:
    def _run(self, argv):
        from unittest.mock import AsyncMock
        from TTS_ka.main import main
        with patch("sys.argv", ["TTS_ka", *argv, "--lang", "en", "--no-play"]), \
             patch("TTS_ka.main.fast_generate_audio", new=AsyncMock(return_value=True)) as mfa, \
             patch("TTS_ka.main.get_optimal_settings",
                   return_value={"method": "direct", "chunk_seconds": 0, "parallel": 1}):
            try:
                main()
            except SystemExit as exc:
                return exc.code, mfa
        return 0, mfa

    def test_speaks_only_the_selected_pages(self, tmp_path):
        f = tmp_path / "book.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        fake_pypdf, _ = _fake_pdf(["Intro text.", "Chapter two text.", "Index."])
        with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
            code, mfa = self._run([str(f), "--pages", "2", "-o", str(tmp_path / "o.mp3")])
        assert code == 0
        assert mfa.call_args.args[0] == "Chapter two text."

    def test_out_of_range_exits_2(self, tmp_path, capsys):
        f = tmp_path / "book.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        fake_pypdf, _ = _fake_pdf(["a", "b"])
        with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
            code, mfa = self._run([str(f), "--pages", "5"])
        assert code == 2
        assert not mfa.called
        assert "--pages: page 5 is past the end" in capsys.readouterr().err

    def test_text_input_exits_2(self, capsys):
        code, mfa = self._run(["Just some words to speak", "--pages", "1"])
        assert code == 2
        assert not mfa.called
        assert "--pages needs a PDF file" in capsys.readouterr().err

    def test_non_pdf_file_exits_2(self, tmp_path, capsys):
        f = tmp_path / "notes.txt"
        f.write_text("hello", encoding="utf-8")
        code, mfa = self._run([str(f), "--pages", "1"])
        assert code == 2
        assert not mfa.called
        assert "only works with PDF" in capsys.readouterr().err


class _FakePoppler:
    """Stands in for ``subprocess.run`` of pdftotext / pdfinfo over a list of page texts."""

    def __init__(self, page_texts, pdfinfo=True, pdftotext_rc=0):
        self.pages = page_texts
        self.pdfinfo = pdfinfo
        self.pdftotext_rc = pdftotext_rc
        self.calls = []

    def which(self, name):
        if name == "pdfinfo" and not self.pdfinfo:
            return None
        return f"/usr/bin/{name}"

    def run(self, argv, **_kwargs):
        from subprocess import CompletedProcess
        self.calls.append(argv)
        if argv[0].endswith("pdfinfo"):
            return CompletedProcess(argv, 0, f"Title: x\nPages:          {len(self.pages)}\n".encode())
        first, last = 1, len(self.pages)
        if "-f" in argv:
            first = int(argv[argv.index("-f") + 1])
            last = int(argv[argv.index("-l") + 1])
        out = "".join(t + "\f" for t in self.pages[first - 1:last])
        return CompletedProcess(argv, self.pdftotext_rc, out.encode("utf-8"))


@pytest.fixture
def poppler(monkeypatch):
    def install(page_texts, **kwargs):
        fake = _FakePoppler(page_texts, **kwargs)
        monkeypatch.setattr(pdf_reader, "_pdftotext_exe", lambda: "/usr/bin/pdftotext")
        monkeypatch.setattr(pdf_reader.shutil, "which", fake.which)
        monkeypatch.setattr(pdf_reader.subprocess, "run", fake.run)
        return fake
    return install


class TestSoftHyphenRepair:
    @pytest.mark.parametrize("raw, expected", [
        ("very dif\xadfer\xadent", "very different"),
        ("hard prob\xadlems \xadbecause", "hard problems because"),
        ("and\n\xadr unning scripts", "and\nrunning scripts"),     # stray space after the glyph
        ("impor\xadt ant", "important"),
        ("repre\xadsen\xadt a\xadtion", "representation"),
        ("big-\xadO notation", "big-O notation"),                # after a hyphen: own word
        ("rm -\xadf out2.txt", "rm -f out2.txt"),
        ("a sequence\u2014\xada worklist", "a sequence\u2014a worklist"),
        ("plain text", "plain text"),
    ])
    def test_repair(self, raw, expected):
        assert pdf_reader._repair_soft_hyphens(raw) == expected


class TestPdftotext:
    def test_whole_document_is_preferred_over_pypdf(self, tmp_path, poppler):
        f = tmp_path / "book.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        fake = poppler(["Intro dif\xadfer\xadent.", "", "Chapter one."])
        with patch.dict(sys.modules, {"pypdf": None}):   # pypdf not needed
            assert read_file(str(f)) == "Intro different.\n\nChapter one."
        assert fake.calls == [["/usr/bin/pdftotext", "-enc", "UTF-8", str(f), "-"]]

    def test_pages_extract_only_the_span_needed(self, tmp_path, poppler):
        f = tmp_path / "book.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        fake = poppler([f"page {n}" for n in range(1, 11)])
        assert read_file(str(f), pages="7,4-5") == "page 7\n\npage 4\n\npage 5"
        pdftotext_call = fake.calls[-1]
        assert pdftotext_call[pdftotext_call.index("-f") + 1] == "4"
        assert pdftotext_call[pdftotext_call.index("-l") + 1] == "7"

    def test_pages_without_pdfinfo_counts_from_full_text(self, tmp_path, poppler):
        from TTS_ka.readers import PageRangeError
        f = tmp_path / "book.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        poppler(["a", "b", "c"], pdfinfo=False)
        assert read_file(str(f), pages="2-") == "b\n\nc"
        with pytest.raises(PageRangeError, match="has 3 pages"):
            read_file(str(f), pages="4")

    def test_out_of_range_uses_pdfinfo_count(self, tmp_path, poppler):
        from TTS_ka.readers import PageRangeError
        f = tmp_path / "book.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        poppler(["a", "b"])
        with pytest.raises(PageRangeError, match="has 2 pages"):
            read_file(str(f), pages="1-3")

    def test_failure_falls_back_to_pypdf(self, tmp_path, poppler):
        f = tmp_path / "book.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        poppler(["ignored"], pdftotext_rc=1)
        fake_pypdf, _ = _fake_pdf(["from pypdf"])
        with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
            assert read_file(str(f)) == "from pypdf"
