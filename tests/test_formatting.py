"""Integration tests for the formatting module."""

from aavaaz.features.formatting import (
    _capitalize_sentences,
    _collapse_whitespace,
    _replace_spoken_numbers,
    _words_to_number,
    apply_replacements,
    compile_replacements,
    format_transcript,
    smart_format,
)


class TestSpokenNumbers:
    def test_simple_number(self):
        assert _replace_spoken_numbers("I have twenty one apples") == "I have 21 apples"

    def test_large_number(self):
        assert _replace_spoken_numbers("one thousand two hundred thirty four") == "1234"

    def test_hundred(self):
        assert _replace_spoken_numbers("three hundred") == "300"

    def test_million(self):
        assert _replace_spoken_numbers("two million") == "2000000"

    def test_no_number_words(self):
        assert _replace_spoken_numbers("hello world") == "hello world"

    def test_number_with_punctuation(self):
        result = _replace_spoken_numbers("I have twenty one.")
        assert "21" in result

    def test_no_merge_across_sentence(self):
        # a number must not span a sentence boundary
        assert _replace_spoken_numbers("I have two. Three cats") == "I have 2. 3 cats"

    def test_no_merge_of_adjacent_numbers(self):
        assert _replace_spoken_numbers("three thirty") == "3 30"
        assert _replace_spoken_numbers("four fifteen") == "4 15"

    def test_spoken_year(self):
        assert _replace_spoken_numbers("nineteen eighty four") == "1984"
        assert _replace_spoken_numbers("in twenty twenty three") == "in 2023"

    def test_capitalized_number(self):
        assert _replace_spoken_numbers("Twenty one apples") == "21 apples"

    def test_words_to_number_empty(self):
        assert _words_to_number([]) is None

    def test_words_to_number_and_only(self):
        assert _words_to_number(["and"]) is None


class TestCapitalization:
    def test_start_of_string(self):
        assert _capitalize_sentences("hello") == "Hello"

    def test_after_period(self):
        assert _capitalize_sentences("done. next") == "Done. Next"

    def test_after_question(self):
        assert _capitalize_sentences("what? really") == "What? Really"

    def test_empty(self):
        assert _capitalize_sentences("") == ""


class TestCollapseWhitespace:
    def test_multiple_spaces(self):
        assert _collapse_whitespace("hello    world") == "hello world"

    def test_leading_trailing(self):
        assert _collapse_whitespace("  hi  ") == "hi"


class TestFormatTranscript:
    def test_all_options(self):
        result = format_transcript("  hello world.  how  are you  ", capitalize=True, numbers=False)
        assert result.startswith("Hello")
        assert "  " not in result

    def test_numbers_enabled(self):
        result = format_transcript("I have twenty apples", numbers=True)
        assert "20" in result

    def test_empty(self):
        assert format_transcript("") == ""

    def test_none(self):
        assert format_transcript(None) is None


class TestSmartFormat:
    def test_currency(self):
        result = smart_format("50 dollars")
        assert "$50" in result

    def test_percentage(self):
        result = smart_format("50 percent")
        assert "50%" in result

    def test_ordinal_prose_unchanged(self):
        # 'second' as a common word must survive smart formatting
        assert smart_format("give me a second") == "give me a second"

    def test_ordinal_in_date(self):
        assert "2nd" in smart_format("May second")

    def test_removes_space_before_punctuation(self):
        assert smart_format("hello , world .") == "hello, world."

    def test_adds_space_after_punctuation(self):
        assert smart_format("hello,world.Bye") == "hello, world. Bye"

    def test_collapses_repeated_terminal_marks(self):
        assert smart_format("wow!! really??") == "wow! really?"
        assert smart_format("done.. now") == "done. now"

    def test_keeps_ellipsis(self):
        assert smart_format("wait... ok") == "wait... ok"

    def test_collapses_double_commas(self):
        assert smart_format("one,, two") == "one, two"

    def test_spoken_time(self):
        assert format_transcript("meet at three thirty pm", smart=True) == "Meet at 3:30 PM"
        assert format_transcript("call at four forty five", smart=True) == "Call at 4:45"

    def test_leaves_numeric_punctuation_alone(self):
        assert smart_format("3:30 PM costs 1.5") == "3:30 PM costs 1.5"


class TestReplacements:
    def test_plain_rule_ignores_case(self):
        rules = compile_replacements(plain=[("cube ernestes", "Kubernetes")], regex=[])
        assert apply_replacements("Cube Ernestes runs it", rules) == "Kubernetes runs it"

    def test_plain_rule_skips_matches_inside_words(self):
        rules = compile_replacements(plain=[("ai", "AI")], regex=[])
        assert apply_replacements("she said ai helps", rules) == "she said AI helps"

    def test_plain_replacement_keeps_backslashes(self):
        rules = compile_replacements(plain=[("share", r"\\server\share")], regex=[])
        assert apply_replacements("open share now", rules) == r"open \\server\share now"

    def test_regex_rule_uses_groups(self):
        rules = compile_replacements(plain=[], regex=[(r"ticket (\d+)", r"#\1")])
        assert apply_replacements("see ticket 42", rules) == "see #42"
