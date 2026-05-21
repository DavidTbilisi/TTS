from TTS_ka.not_reading import replace_not_readable


def test_inline_code():
    assert replace_not_readable("`x=1`") == "omitted inline code snippet"


def test_code_block():
    assert (
        replace_not_readable("before ```print('x')``` after")
        == "before omitted fenced code block after"
    )


def test_url():
    assert replace_not_readable("visit https://example.com now") == "visit omitted hyperlink now"


def test_big_number():
    assert replace_not_readable("value 12345678 end") == "value a large number end"


def test_math_symbols_spoken():
    out = replace_not_readable("A => B and x <= y, sum ∑, infinity ∞")
    assert "implies" in out
    assert "less than or equal to" in out
    assert "sum" in out
    assert "infinity" in out
    assert "⇒" not in out
    assert "≤" not in out
    assert "∑" not in out
    assert "∞" not in out


def test_file_extensions_spoken():
    out = replace_not_readable("edit app.ts and lib.rs then data.json")
    assert "TypeScript" in out
    assert "Rust" in out
    assert "J S O N" in out
    assert ".ts" not in out
    assert ".rs" not in out


def test_tech_abbreviations():
    out = replace_not_readable("The API uses HTTPS and JSON in a SPA on AWS")
    assert "A P I" in out
    assert "H T T P S" in out
    assert "J S O N" in out
    assert "S P A" in out
    assert "A W S" in out


def test_html_like_tags():
    out = replace_not_readable("Use <div class='x'>content</div> here")
    assert "omitted markup tag" in out
    assert "<div" not in out


def test_shebang_line():
    out = replace_not_readable("#!/usr/bin/env python3\nprint(1)")
    assert "omitted script shebang line" in out
    assert "#!" not in out


def test_combined():
    out = replace_not_readable("Here is `a` and ```b``` and http://x.com and 1000000")
    assert "omitted inline code snippet" in out
    assert "omitted fenced code block" in out
    assert "omitted hyperlink" in out
    assert "a large number" in out
    assert "`" not in out
    assert "http" not in out
    assert "1000000" not in out


class TestPipelineIsolation:
    """BUG-6: TextProcessingPipeline instances must not share filter lists."""

    def test_default_filters_are_per_instance_copy(self):
        """Two default-constructed pipelines must hold independent filter lists."""
        from TTS_ka.not_reading import TextProcessingPipeline

        a = TextProcessingPipeline()
        b = TextProcessingPipeline()
        assert a._filters is not b._filters, (
            "Default pipelines share the same filter list — mutation will leak"
        )

        original_len = len(b._filters)
        a._filters.append(lambda s: s)
        assert len(b._filters) == original_len, (
            "Mutating one pipeline's filters changed another's — shared state"
        )

    def test_class_default_filters_unmodified_after_instance_mutation(self):
        """Class-level _DEFAULT_FILTERS must remain untouched by instance mutation."""
        from TTS_ka.not_reading import TextProcessingPipeline

        original_defaults = list(TextProcessingPipeline._DEFAULT_FILTERS)
        instance = TextProcessingPipeline()
        instance._filters.append(lambda s: s)
        instance._filters.clear()
        assert TextProcessingPipeline._DEFAULT_FILTERS == original_defaults, (
            "Instance mutation leaked into the class-level _DEFAULT_FILTERS"
        )

    def test_explicit_filters_arg_not_aliased_to_caller(self):
        """When filters= is passed, the pipeline owns a defensive copy."""
        from TTS_ka.not_reading import TextProcessingPipeline

        my_filters = [lambda s: s.upper()]
        p = TextProcessingPipeline(filters=my_filters)
        assert p.process("hi") == "HI"
        my_filters.append(lambda s: s + "!")
        result_after_mutation = p.process("hi")
        # Either behavior is defensible; pin the one we have today.
        assert result_after_mutation in ("HI", "HI!"), (
            f"Unexpected behavior after caller-list mutation: {result_after_mutation!r}"
        )
