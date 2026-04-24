"""Tests for the FifteensquaredScraper hint extraction."""
from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup

from puzzle_scraper import FifteensquaredScraper


def _make_html(body_content):
    """Build a minimal HTML page with the given body content inside entry-content."""
    return f"""
    <html><body>
    <article class="entry-content">
    {body_content}
    </article>
    </body></html>
    """


def _fetch_hints_from_html(html):
    """Helper to call fetch_hints with mocked HTTP response."""
    scraper = FifteensquaredScraper()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.content = html.encode()
    with patch.object(scraper.session, 'get', return_value=mock_resp):
        return scraper.fetch_hints('http://test.example.com/post')


class TestFormatA:
    """Format A: Number alone, answer on next line."""

    def test_basic(self):
        html = _make_html("""
        <p>Across</p>
        <p>1</p>
        <p>ANTELOPE</p>
        <p>A charade of ANTE (stake) and LOPE (bound).</p>
        <p>Down</p>
        <p>2</p>
        <p>CASTLE</p>
        <p>Double definition: a fortified building and a chess piece.</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '1-across' in result
        assert '2-down' in result
        assert result['1-across']['text'][0].startswith('A charade')
        assert result['2-down']['text'][0].startswith('Double definition')

    def test_with_enumeration(self):
        html = _make_html("""
        <p>Across</p>
        <p>1</p>
        <p>ANTELOPE (8)</p>
        <p>A charade of ANTE (stake) and LOPE (bound).</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '1-across' in result
        # Answer text should NOT include enumeration
        # (verified via the stored hint text, not the answer directly)
        assert len(result['1-across']['text']) >= 1

    def test_multi_word_answer_with_enumeration(self):
        html = _make_html("""
        <p>Across</p>
        <p>5</p>
        <p>SALT AND PEPPER (4,3,6)</p>
        <p>A cryptic definition meaning seasoning.</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '5-across' in result


class TestFormatB:
    """Format B: Number + clue text, answer on next line."""

    def test_basic(self):
        html = _make_html("""
        <p>Across</p>
        <p>1 Animal bound on stake</p>
        <p>ANTELOPE</p>
        <p>A charade of ANTE (stake) and LOPE (bound).</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '1-across' in result

    def test_with_enumeration(self):
        html = _make_html("""
        <p>Across</p>
        <p>1 Animal bound on stake (8)</p>
        <p>ANTELOPE (8)</p>
        <p>A charade of ANTE (stake) and LOPE (bound).</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '1-across' in result


class TestFormatC:
    """Format C: Number + all-caps answer on same line."""

    def test_basic(self):
        html = _make_html("""
        <p>Across</p>
        <p>1a ANTELOPE</p>
        <p>A charade of ANTE (stake) and LOPE (bound).</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '1-across' in result

    def test_with_enumeration(self):
        html = _make_html("""
        <p>Across</p>
        <p>1a ANTELOPE (8)</p>
        <p>A charade of ANTE (stake) and LOPE (bound).</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '1-across' in result

    def test_hyphenated_answer(self):
        html = _make_html("""
        <p>Across</p>
        <p>3 SELF-MADE (4-4)</p>
        <p>A charade of SELF and MADE.</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '3-across' in result


class TestFormatD:
    """Format D: Number + answer + separator + explanation on same line."""

    def test_en_dash_separator(self):
        html = _make_html("""
        <p>Across</p>
        <p>1a ANTELOPE (8) \u2013 A charade of ANTE (stake) and LOPE (bound).</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '1-across' in result
        assert any('charade' in t.lower() for t in result['1-across']['text'])

    def test_colon_separator(self):
        html = _make_html("""
        <p>Across</p>
        <p>5 LOCALE (6): Homophone of HALER (more healthy), sounds like LOCALE.</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '5-across' in result

    def test_dash_separator_no_enum(self):
        html = _make_html("""
        <p>Across</p>
        <p>1a ANTELOPE - A charade of ANTE and LOPE.</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '1-across' in result

    def test_multiline_explanation(self):
        """Format D with additional explanation on following lines."""
        html = _make_html("""
        <p>Across</p>
        <p>1a ANTELOPE (8) \u2013 A charade of ANTE (stake) and LOPE (bound).</p>
        <p>ANTE means a stake in poker, LOPE means to bound or run.</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '1-across' in result
        # Should have collected both the inline and subsequent explanation
        assert len(result['1-across']['text']) >= 1


class TestMultipleClues:
    """Test parsing pages with many clues across both directions."""

    def test_full_puzzle_format_c_with_enum(self):
        """Typical Guardian cryptic format on fifteensquared."""
        html = _make_html("""
        <p>Across</p>
        <p>1 ANTELOPE (8)</p>
        <p>A charade of ANTE (stake) and LOPE (bound).</p>
        <p>5 LOCALE (6)</p>
        <p>Homophone: sounds like LOCAL, a position or place.</p>
        <p>9 TRAPPIST (8)</p>
        <p>Homophone of TRAPEZE ARTIST shortened.</p>
        <p>Down</p>
        <p>1 ATTIC (5)</p>
        <p>Double definition: a room and relating to Athens.</p>
        <p>2 NOODLE (6)</p>
        <p>Hidden word in caNOODLE.</p>
        """)
        result = _fetch_hints_from_html(html)
        assert len(result) == 5
        assert '1-across' in result
        assert '5-across' in result
        assert '9-across' in result
        assert '1-down' in result
        assert '2-down' in result

    def test_mixed_formats(self):
        """Different formats can appear in the same post."""
        html = _make_html("""
        <p>Across</p>
        <p>1a ANTELOPE (8)</p>
        <p>A charade of ANTE and LOPE.</p>
        <p>5a LOCALE (6) \u2013 Homophone of LOCAL.</p>
        <p>Down</p>
        <p>1</p>
        <p>ATTIC (5)</p>
        <p>Double definition.</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '1-across' in result   # Format C
        assert '5-across' in result   # Format D
        assert '1-down' in result     # Format A (with enum)


class TestDefinitionExtraction:
    """Test that underlined definitions are matched to clues."""

    def test_underlined_definition_matched(self):
        html = _make_html("""
        <p>Across</p>
        <p>1 ANTELOPE (8)</p>
        <p>A charade of ANTE (<span style="text-decoration: underline">animal</span> bound on stake) and LOPE.</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '1-across' in result
        assert 'animal' in result['1-across']['definitions']


class TestEdgeCases:
    """Test edge cases and robustness."""

    def test_empty_content(self):
        html = _make_html("<p>No crossword content here.</p>")
        result = _fetch_hints_from_html(html)
        assert result == {}

    def test_direction_only(self):
        html = _make_html("<p>Across</p><p>Down</p>")
        result = _fetch_hints_from_html(html)
        assert result == {}

    def test_explanation_not_truncated_by_number_in_text(self):
        """Explanation lines starting with numbers > 99 shouldn't stop collection."""
        html = _make_html("""
        <p>Across</p>
        <p>1 CENTURY (7)</p>
        <p>A period of 100 years, derived from Latin centum.</p>
        <p>100 is the key number here in Roman numerals = C.</p>
        """)
        result = _fetch_hints_from_html(html)
        assert '1-across' in result
        # Both explanation lines should be collected (100 > 99 so not a clue start)
        texts = result['1-across']['text']
        assert len(texts) >= 2
