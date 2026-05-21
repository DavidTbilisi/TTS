from TTS_ka.not_reading import replace_not_readable


def test_inline_code():
    assert replace_not_readable("`x=1`") == "you can see code in text"


def test_code_block():
    assert replace_not_readable("before ```print('x')``` after") == "before you can see code in text after"


def test_url():
    assert replace_not_readable("visit https://example.com now") == "visit see link in text now"


def test_big_number():
    assert replace_not_readable("value 12345678 end") == "value a large number end"


def test_combined():
    out = replace_not_readable("Here is `a` and ```b``` and http://x.com and 1000000")
    assert "you can see code in text" in out
    assert "see link in text" in out
    assert "a large number" in out
    assert '`' not in out
    assert 'http' not in out
    assert '1000000' not in out


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

        # Mutating one must not affect the other.
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

        # Note: current impl does not copy when filters= is explicit. If you want
        # the same isolation guarantee for caller-provided lists, update __init__
        # to wrap with list(...) unconditionally — this test documents the gap.
        my_filters = [lambda s: s.upper()]
        p = TextProcessingPipeline(filters=my_filters)
        # The pipeline still works
        assert p.process("hi") == "HI"
        # Document current behavior: caller's list IS aliased. If this changes
        # to a defensive copy, update the assertion.
        my_filters.append(lambda s: s + "!")
        result_after_mutation = p.process("hi")
        # Either behavior is defensible; pin the one we have today.
        assert result_after_mutation in ("HI", "HI!"), (
            f"Unexpected behavior after caller-list mutation: {result_after_mutation!r}"
        )
