from TTS_ka.not_reading import replace_not_readable


def test_inline_code():
    assert replace_not_readable("`x=1`") == "you can see code in text"


def test_code_block():
    assert (
        replace_not_readable("before ```print('x')``` after")
        == "before you can see code in text after"
    )


def test_url():
    assert replace_not_readable("visit https://example.com now") == "visit see link in text now"


def test_big_number():
    assert replace_not_readable("value 12345678 end") == "value a large number end"


def test_combined():
    out = replace_not_readable("Here is `a` and ```b``` and http://x.com and 1000000")
    assert "you can see code in text" in out
    assert "see link in text" in out
    assert "a large number" in out
    assert "`" not in out
    assert "http" not in out
    assert "1000000" not in out
