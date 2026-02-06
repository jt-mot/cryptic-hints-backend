"""Tests for the EnhancedHintGenerator."""
import json
import os
from unittest.mock import patch, MagicMock

from enhanced_hints import EnhancedHintGenerator


class TestHintGeneratorInit:
    def test_defaults(self):
        gen = EnhancedHintGenerator(use_claude=False)
        assert gen.total_api_calls == 0
        assert gen.total_input_tokens == 0
        assert gen.total_output_tokens == 0
        assert gen.model_used is None

    def test_usage_stats_empty(self):
        gen = EnhancedHintGenerator(use_claude=False)
        stats = gen.get_usage_stats()
        assert stats['api_calls'] == 0
        assert stats['estimated_cost_usd'] == 0.0

    def test_reset_usage_stats(self):
        gen = EnhancedHintGenerator(use_claude=False)
        gen.total_api_calls = 5
        gen.total_input_tokens = 1000
        gen.total_output_tokens = 500
        gen.model_used = 'test-model'
        gen.reset_usage_stats()
        assert gen.total_api_calls == 0
        assert gen.total_input_tokens == 0
        assert gen.total_output_tokens == 0
        assert gen.model_used is None


class TestHintGeneratorFallback:
    """Tests for regex fallback when Claude is disabled."""

    def test_no_paragraphs_no_context_returns_defaults(self):
        gen = EnhancedHintGenerator(use_claude=False)
        hints = gen.generate_hints([], 'generic')
        assert len(hints) == 4
        assert 'clue structure' in hints[0].lower()

    def test_with_paragraphs_returns_four_hints(self):
        gen = EnhancedHintGenerator(use_claude=False)
        paragraphs = [
            'The definition is "to travel".',
            'This is an anagram of RIDE.',
            'Take the letters of RIDE and rearrange.',
            'DIRE means "to travel" - an anagram of RIDE.'
        ]
        hints = gen.generate_hints(paragraphs, 'generic',
                                   clue_text='Terrible ride to travel (4)',
                                   answer='DIRE')
        assert len(hints) == 4
        # All hints should be non-empty strings
        for h in hints:
            assert isinstance(h, str)
            assert len(h) > 0


class TestHintGeneratorClaude:
    """Tests for Claude API integration and token tracking."""

    def test_successful_api_call_tracks_tokens(self):
        gen = EnhancedHintGenerator(use_claude=True)
        gen.api_key = 'test-key'

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'content': [{'text': json.dumps({
                'hint1': 'Definition hint',
                'hint2': 'Wordplay hint',
                'hint3': 'Construction hint',
                'hint4': 'Full explanation',
            })}],
            'usage': {
                'input_tokens': 500,
                'output_tokens': 200,
            },
            'model': 'claude-sonnet-4-20250514',
        }

        with patch('enhanced_hints.requests.post', return_value=mock_response):
            hints = gen.generate_hints(
                ['Some explanation text'],
                'generic',
                clue_text='Test clue (4)',
                answer='TEST',
            )

        assert hints == ['Definition hint', 'Wordplay hint',
                         'Construction hint', 'Full explanation']
        assert gen.total_api_calls == 1
        assert gen.total_input_tokens == 500
        assert gen.total_output_tokens == 200
        assert gen.model_used == 'claude-sonnet-4-20250514'

    def test_api_failure_falls_back_to_regex(self):
        gen = EnhancedHintGenerator(use_claude=True)
        gen.api_key = 'test-key'

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch('enhanced_hints.requests.post', return_value=mock_response):
            hints = gen.generate_hints(
                ['The definition is "a dog". Anagram of GOD.'],
                'generic',
                clue_text='Deity is a dog (3)',
                answer='GOD',
            )

        # Should still get 4 hints from regex fallback
        assert len(hints) == 4
        # No API calls should be counted on failure
        assert gen.total_api_calls == 0

    def test_cost_calculation(self):
        gen = EnhancedHintGenerator(use_claude=False)
        gen.total_input_tokens = 1_000_000
        gen.total_output_tokens = 100_000
        stats = gen.get_usage_stats()
        # $3 per MTok input + $15 per MTok output * 0.1 = $3 + $1.50 = $4.50
        assert abs(stats['estimated_cost_usd'] - 4.5) < 0.001

    def test_multiple_calls_accumulate(self):
        gen = EnhancedHintGenerator(use_claude=True)
        gen.api_key = 'test-key'

        def make_mock(input_tok, output_tok):
            m = MagicMock()
            m.status_code = 200
            m.json.return_value = {
                'content': [{'text': json.dumps({
                    'hint1': 'h1', 'hint2': 'h2',
                    'hint3': 'h3', 'hint4': 'h4',
                })}],
                'usage': {
                    'input_tokens': input_tok,
                    'output_tokens': output_tok,
                },
                'model': 'claude-sonnet-4-20250514',
            }
            return m

        with patch('enhanced_hints.requests.post',
                   side_effect=[make_mock(100, 50), make_mock(200, 80)]):
            gen.generate_hints(['text'], 'generic',
                               clue_text='Clue 1', answer='ANS')
            gen.generate_hints(['text'], 'generic',
                               clue_text='Clue 2', answer='ANS')

        assert gen.total_api_calls == 2
        assert gen.total_input_tokens == 300
        assert gen.total_output_tokens == 130
