"""Tests for PagePatternParser."""

from ocr.utils.page_parser import PagePatternParser


class TestParsePattern:
    """Tests for parse_pattern method."""

    def test_empty_pattern_returns_all_pages(self):
        assert PagePatternParser.parse_pattern("", 5) == {1, 2, 3, 4, 5}

    def test_none_pattern_returns_all_pages(self):
        assert PagePatternParser.parse_pattern(None, 3) == {1, 2, 3}

    def test_single_page(self):
        assert PagePatternParser.parse_pattern("3", 10) == {3}

    def test_page_range(self):
        assert PagePatternParser.parse_pattern("1-3", 10) == {1, 2, 3}

    def test_open_ended_range_start(self):
        assert PagePatternParser.parse_pattern("5-", 7) == {5, 6, 7}

    def test_open_ended_range_end(self):
        assert PagePatternParser.parse_pattern("-3", 10) == {1, 2, 3}

    def test_multiple_parts(self):
        assert PagePatternParser.parse_pattern("1-3,5,7-", 8) == {1, 2, 3, 5, 7, 8}

    def test_out_of_range_clamped(self):
        result = PagePatternParser.parse_pattern("100", 5)
        assert result == set()

    def test_keyword_all(self):
        assert PagePatternParser.parse_pattern("all", 10) == set(range(1, 11))

    def test_keyword_star(self):
        assert PagePatternParser.parse_pattern("*", 5) == {1, 2, 3, 4, 5}

    def test_keyword_pg1(self):
        assert PagePatternParser.parse_pattern("pg1", 10) == {1}

    def test_keyword_first(self):
        assert PagePatternParser.parse_pattern("first", 10) == {1}

    def test_keyword_case_insensitive(self):
        assert PagePatternParser.parse_pattern("ALL", 3) == {1, 2, 3}
        assert PagePatternParser.parse_pattern("PG1", 3) == {1}

    def test_keyword_with_whitespace(self):
        assert PagePatternParser.parse_pattern("  all  ", 3) == {1, 2, 3}


class TestValidatePattern:
    """Tests for validate_pattern method."""

    def test_empty_is_valid(self):
        assert PagePatternParser.validate_pattern("") is True

    def test_single_number_valid(self):
        assert PagePatternParser.validate_pattern("5") is True

    def test_range_valid(self):
        assert PagePatternParser.validate_pattern("1-3") is True

    def test_open_range_valid(self):
        assert PagePatternParser.validate_pattern("5-") is True

    def test_complex_valid(self):
        assert PagePatternParser.validate_pattern("1-3,5,7-") is True

    def test_invalid_chars(self):
        assert PagePatternParser.validate_pattern("abc") is False

    def test_keyword_all_valid(self):
        assert PagePatternParser.validate_pattern("all") is True

    def test_keyword_star_valid(self):
        assert PagePatternParser.validate_pattern("*") is True

    def test_keyword_pg1_valid(self):
        assert PagePatternParser.validate_pattern("pg1") is True

    def test_keyword_first_valid(self):
        assert PagePatternParser.validate_pattern("first") is True
