"""
Enhanced Hint Generation System

Handles different fifteensquared author styles and produces better progressive hints
Uses Claude API for intelligent hint generation with regex fallback
"""

import re
import os
import json
from typing import List, Dict, Optional, Tuple

# Try to import requests for API calls
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# Comprehensive cryptic crossword technique patterns
WORDPLAY_TECHNIQUES = {
    'anagram': {
        'keywords': ['anagram', 'mixed', 'confused', 'scrambled', 'broken', 'shattered',
                     'rearranged', 'sorted', 'shuffled', 'mangled', 'disrupted', 'reworked',
                     'rebuilt', 'reformed', 'reshaped', 'cocktail', 'drunk', 'crazy', 'wild',
                     'destroyed', 'damaged', 'ruined', 'badly', 'off', 'wrong', 'poor'],
        'hint': "This clue uses an anagram - look for an anagram indicator and letters to rearrange",
        'partial': "Rearrange some letters from the clue"
    },
    'hidden': {
        'keywords': ['hidden', 'concealed', 'buried', 'lurking', 'embedded', 'within',
                     'inside', 'some of', 'part of', 'held by', 'contained in', 'partially'],
        'hint': "The answer is hidden within the clue text itself",
        'partial': "Look for the answer spelled out consecutively within the words"
    },
    'reversal': {
        'keywords': ['reversal', 'reversed', 'back', 'backward', 'returned', 'retiring',
                     'reflected', 'flipped', 'overturned', 'up', 'rising', 'going north',
                     'returning', 'retreating', 'revolutionary'],
        'hint': "This is a reversal clue - look for indicators like 'back', 'returned', 'up' (in down clues), or 'west' (in across clues)",
        'partial': "Write something backwards"
    },
    'container': {
        'keywords': ['container', 'envelope', 'around', 'outside', 'wrapping', 'holding',
                     'embracing', 'clutching', 'grasping', 'containing', 'swallowing',
                     'surrounding', 'boxing', 'circling'],
        'hint': "This is a container clue - look for indicators like 'around', 'holding', 'outside', 'embracing' where one part wraps around another",
        'partial': "Put one component inside or around another"
    },
    'insertion': {
        'keywords': ['insertion', 'inserted', 'entering', 'going into', 'put in',
                     'placed in', 'within', 'into', 'piercing', 'interrupting'],
        'hint': "One part goes inside another to form the answer",
        'partial': "Insert one component into another"
    },
    'homophone': {
        'keywords': ['sounds like', 'homophone', 'we hear', 'audibly', 'aloud', 'spoken',
                     'say', 'said', 'heard', 'orally', 'vocal', 'broadcast', 'on the radio',
                     'reportedly', 'to the ear'],
        'hint': "This is a homophone clue - look for indicators like 'we hear', 'sounds like', 'say', 'aloud', or 'reportedly' - the answer sounds like another word",
        'partial': "Think about what the answer sounds like when spoken"
    },
    'double_definition': {
        'keywords': ['double definition', 'two definitions', 'two meanings', 'twin definitions'],
        'hint': "This is a double definition - two separate meanings for the same answer",
        'partial': "Find a word that has two different meanings matching parts of the clue"
    },
    'charade': {
        'keywords': ['charade', 'followed by', 'after', 'before', 'then', 'next to',
                     'beside', 'with', 'plus', 'and', 'leads to', 'precedes'],
        'hint': "The answer is built by joining parts together in sequence",
        'partial': "Chain together the component parts"
    },
    'deletion': {
        'keywords': ['deletion', 'removing', 'without', 'losing', 'dropping', 'missing',
                     'heartless', 'headless', 'endless', 'beheaded', 'curtailed', 'trimmed',
                     'cut', 'short', 'less', 'lacking', 'loses'],
        'hint': "This is a deletion clue - look for indicators like 'headless' (remove first letter), 'endless' (remove last letter), 'heartless' (remove middle letter), or 'without'",
        'partial': "Take away part of a word"
    },
    'abbreviation': {
        'keywords': ['abbreviation', 'abbrev', 'short for', 'stands for', 'initially',
                     'first letters', 'starts', 'leader', 'head of', 'capital'],
        'hint': "Look for abbreviations or shortened forms",
        'partial': "Use standard abbreviations or initials"
    },
    'initial_letters': {
        'keywords': ['initial', 'initials', 'first letters', 'starts', 'heads', 'leaders',
                     'acrostic', 'opening'],
        'hint': "Take the first letters of certain words",
        'partial': "Look at the initial letters"
    },
    'final_letters': {
        'keywords': ['final letters', 'last letters', 'ends', 'tails', 'terminals', 'finishes'],
        'hint': "Take the last letters of certain words",
        'partial': "Look at the final letters"
    },
    'spoonerism': {
        'keywords': ['spoonerism', 'spooner', 'swap', 'switch'],
        'hint': "This is a spoonerism - swap initial sounds between words",
        'partial': "Switch the beginning sounds of words"
    },
    'cryptic_definition': {
        'keywords': ['cryptic definition', 'whimsical', 'playful definition', '&lit'],
        'hint': "The whole clue is a cryptic definition - think laterally",
        'partial': "The entire clue describes the answer in a tricky way"
    },
    'letter_selection': {
        'keywords': ['odd letters', 'even letters', 'alternate', 'regularly', 'every other'],
        'hint': "Select specific letters (odd, even, or alternating)",
        'partial': "Pick out certain letters based on position"
    },
}

# Common abbreviation mappings for partial hints
COMMON_ABBREVIATIONS = {
    'nothing': 'O/NIL', 'love': 'O', 'zero': 'O', 'duck': 'O',
    'one': 'I/A/UN', 'fifty': 'L', 'hundred': 'C', 'thousand': 'M/K',
    'five': 'V', 'ten': 'X', 'six': 'VI',
    'north': 'N', 'south': 'S', 'east': 'E', 'west': 'W',
    'direction': 'N/S/E/W', 'point': 'N/S/E/W',
    'doctor': 'DR/MB/MD', 'learner': 'L', 'student': 'L',
    'king': 'K/R', 'queen': 'Q/R/ER', 'prince': 'P',
    'church': 'CH/CE', 'sailor': 'AB/TAR', 'soldier': 'GI/RE',
    'article': 'A/AN/THE', 'note': 'DO/RE/MI/FA/SO/LA/TI',
    'quiet': 'P/SH', 'loud': 'F', 'soft': 'P',
    'right': 'R/RT', 'left': 'L', 'ring': 'O',
    'river': 'R/PO/DEE', 'road': 'RD/ST', 'street': 'ST',
}


class AuthorStyleDetector:
    """Detects the author/style of fifteensquared analysis"""

    KNOWN_AUTHORS = {
        'petero': {'style': 'systematic', 'underlines_def': True},
        'verlaine': {'style': 'conversational', 'underlines_def': True},
        'vinyl': {'style': 'concise', 'underlines_def': True},
        'pommers': {'style': 'detailed', 'underlines_def': True},
        'jackkt': {'style': 'thorough', 'underlines_def': True},
        'bertandjoyce': {'style': 'collaborative', 'underlines_def': True},
        'alankd': {'style': 'analytical', 'underlines_def': True},
        'cornick': {'style': 'methodical', 'underlines_def': True},
    }

    @staticmethod
    def detect_author(url: str, content: str) -> str:
        """
        Detect the author from URL or content

        Returns author name or 'generic'
        """
        content_lower = content.lower()

        # Check content for "by AuthorName" pattern (most reliable)
        by_match = re.search(r'(?:at|posted)\s+.*?\s+by\s+([a-z]+)', content_lower, re.IGNORECASE)
        if by_match:
            author = by_match.group(1).lower()
            if author in AuthorStyleDetector.KNOWN_AUTHORS:
                return author

        # Check for author name anywhere in content
        for author in AuthorStyleDetector.KNOWN_AUTHORS:
            if author in content_lower:
                return author

        # Check URL for author name
        url_lower = url.lower()
        for author in AuthorStyleDetector.KNOWN_AUTHORS:
            if author in url_lower:
                return author

        return 'generic'


class EnhancedHintGenerator:
    """Generate progressive hints with author-aware parsing and Claude AI"""

    def __init__(self, use_claude: bool = True):
        self.style_detector = AuthorStyleDetector()
        self.use_claude = use_claude
        self.api_key = os.environ.get('ANTHROPIC_API_KEY')

    def generate_hints(self, hint_paragraphs: List[str], author: str = 'generic',
                       definitions: List[str] = None, clue_text: str = None,
                       answer: str = None) -> List[str]:
        """
        Generate 4-level progressive hints using Claude AI with regex fallback

        Hint Levels:
        - Level 1: Definition (what the answer means)
        - Level 2: Wordplay technique (what type of cryptic device)
        - Level 3: How to construct the answer (without revealing it)
        - Level 4: Full answer and explanation

        Args:
            hint_paragraphs: Raw text paragraphs from fifteensquared analysis
            author: Author name (petero, verlaine, etc.)
            definitions: Extracted HTML definitions (underlined/italicized text)
            clue_text: The original clue text (optional, improves hint quality)
            answer: The answer (optional, improves hint quality)

        Returns:
            List of 4 hints, progressively more revealing
        """
        if not hint_paragraphs:
            return ['Look at the clue structure.',
                    'Identify the wordplay type.',
                    'Break down each part of the clue.',
                    'No explanation available.']

        if definitions is None:
            definitions = []

        full_text = ' '.join(hint_paragraphs)

        # Try Claude API first if enabled and available
        if self.use_claude and self.api_key and REQUESTS_AVAILABLE:
            claude_hints = self._generate_hints_with_claude(
                full_text, definitions, clue_text, answer
            )
            if claude_hints:
                print(f"      Claude API: Generated hints successfully")
                return claude_hints
            print(f"      Claude API: Failed, using regex fallback")
        else:
            # Log why Claude is not being used
            if not self.use_claude:
                print(f"      Claude API: Disabled")
            elif not self.api_key:
                print(f"      Claude API: No ANTHROPIC_API_KEY set")
            elif not REQUESTS_AVAILABLE:
                print(f"      Claude API: requests library not available")

        # Fallback to regex-based hint generation
        return self._generate_hints_with_regex(full_text, hint_paragraphs, definitions, author)

    def _generate_hints_with_claude(self, explanation: str, definitions: List[str],
                                     clue_text: str = None, answer: str = None) -> Optional[List[str]]:
        """
        Use Claude API to generate intelligent progressive hints

        Returns None if API call fails (triggers fallback to regex)
        """
        try:
            # Build the prompt with all available context
            definition_text = definitions[0] if definitions else "unknown"

            prompt = f"""You are helping create progressive hints for a cryptic crossword clue. Your goal is to help solvers learn how cryptic clues work by guiding them step-by-step toward the answer.

CONTEXT:
- Definition (the "straight" part that means the answer): {definition_text}
- Clue text: {clue_text if clue_text else "not provided"}
- Answer: {answer if answer else "not provided"}
- Expert explanation: {explanation}

Generate exactly 4 hints, each more revealing than the last:

HINT 1 - DEFINITION ONLY:
Just state the definition clearly. Example: "Definition: 'cruel'" or "Definition: 'type of bird'"

HINT 2 - TECHNIQUE:
Name the cryptic technique used (anagram, hidden word, reversal, container, homophone, double definition, charade, deletion, etc.) and briefly explain what that technique means. Don't reveal specifics about this clue.
Example: "This is an anagram - look for an indicator word that suggests mixing or rearranging letters"

HINT 3 - HOW TO CONSTRUCT (most important - be helpful but don't give the answer):
Explain the mechanics of how to construct the answer from the clue. Identify:
- The indicator word (if applicable)
- What letters/words to work with
- How they combine
Do NOT reveal the final answer, but make this hint genuinely useful.
Example: "'wild' is the anagram indicator - rearrange the letters of 'PIRATES'"
Example: "'reportedly' signals a homophone - think of a word for 'holy man' that sounds like..."

HINT 4 - FULL ANSWER:
Give the complete answer and full explanation of how it works.
Example: "Answer: TRAPPIST | 'Reportedly' indicates homophone - sounds like 'trapeze artist' = TRAPPIST (type of monk)"

Respond with ONLY a JSON object in this exact format:
{{"hint1": "...", "hint2": "...", "hint3": "...", "hint4": "..."}}"""

            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1000,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('content') and len(data['content']) > 0:
                    text = data['content'][0].get('text', '')

                    # Parse JSON from response
                    # Handle case where response might have markdown code blocks
                    if '```json' in text:
                        text = text.split('```json')[1].split('```')[0]
                    elif '```' in text:
                        text = text.split('```')[1].split('```')[0]

                    hints_data = json.loads(text.strip())

                    return [
                        hints_data.get('hint1', ''),
                        hints_data.get('hint2', ''),
                        hints_data.get('hint3', ''),
                        hints_data.get('hint4', '')
                    ]
            else:
                print(f"      Claude API error: Status {response.status_code} - {response.text[:200]}")

        except requests.exceptions.Timeout:
            print("      Claude API timeout - falling back to regex")
        except json.JSONDecodeError as e:
            print(f"      Claude API JSON parse error: {e} - falling back to regex")
        except Exception as e:
            print(f"      Claude API error: {e} - falling back to regex")

        return None

    def _generate_hints_with_regex(self, full_text: str, hint_paragraphs: List[str],
                                    definitions: List[str], author: str) -> List[str]:
        """
        Fallback regex-based hint generation when Claude is unavailable
        """
        hint_1 = self._generate_definition_hint(full_text, paragraphs=hint_paragraphs,
                                                 definitions=definitions, author=author)
        hint_2 = self._generate_technique_hint(full_text, paragraphs=hint_paragraphs)
        hint_3 = self._generate_structural_hint(full_text, paragraphs=hint_paragraphs,
                                                 definitions=definitions)
        hint_4 = self._generate_full_explanation(hint_paragraphs, definitions)

        return [hint_1, hint_2, hint_3, hint_4]

    def _generate_definition_hint(self, full_text: str, paragraphs: List[str],
                                   definitions: List[str], author: str) -> str:
        """
        Level 1: Show the definition directly

        The definition is the "straight" part of the clue that directly means the answer.
        When we have it from the underlined text, show it directly.
        """
        # Use extracted HTML definitions (underlined text) - most reliable
        if definitions:
            if len(definitions) == 1:
                return f"Definition: '{definitions[0]}'"
            else:
                # Multiple definitions - double definition clue
                return f"Definitions: '{definitions[0]}' and '{definitions[1]}'"

        # Fallback: Check for explicit definition indicators in the text
        def_patterns = [
            r'definition[:\s]+["\']?([^"\'.,]+)["\']?',
            r'def\.?[:\s]+["\']?([^"\'.,]+)["\']?',
        ]

        for pattern in def_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                return f"Definition: '{match.group(1).strip()}'"

        # Check for double definition clues
        if 'double definition' in full_text.lower() or 'two definitions' in full_text.lower():
            return "This is a double definition - find a word with two meanings"

        # Default fallback
        return "Look for the definition at the start or end of the clue"

    def _generate_technique_hint(self, full_text: str, paragraphs: List[str]) -> str:
        """
        Level 2: Identify the wordplay technique(s)

        This should tell the solver what type of cryptic device is being used
        without revealing how it applies to the specific answer.
        """
        text_lower = full_text.lower()

        # Primary technique keywords - these are definitive indicators
        # If we see "anagram" explicitly, it's definitely an anagram
        primary_indicators = {
            'anagram': ['anagram'],
            'hidden': ['hidden word', 'hidden in', 'concealed in'],
            'reversal': ['reversal', 'reversed'],
            'container': ['container', 'envelope'],
            'homophone': ['homophone', 'sounds like', 'we hear'],
            'double_definition': ['double definition', 'two definitions'],
            'deletion': ['deletion'],
            'spoonerism': ['spoonerism'],
        }

        # Check for primary indicators first - these are definitive
        for tech_name, indicators in primary_indicators.items():
            for indicator in indicators:
                if indicator in text_lower:
                    return WORDPLAY_TECHNIQUES[tech_name]['hint']

        # Secondary detection using keyword scoring (less certain)
        technique_scores: Dict[str, int] = {}
        for tech_name, tech_info in WORDPLAY_TECHNIQUES.items():
            score = 0
            for keyword in tech_info['keywords']:
                if keyword in text_lower:
                    # Weight multi-word keywords higher
                    score += len(keyword.split())
            if score > 0:
                technique_scores[tech_name] = score

        # Filter out low-confidence matches
        # Deletion needs high score to avoid false positives from words like "short"
        if 'deletion' in technique_scores and technique_scores['deletion'] < 3:
            del technique_scores['deletion']
        # Charade keywords are very common, require higher threshold
        if 'charade' in technique_scores and technique_scores['charade'] < 4:
            del technique_scores['charade']

        # Sort by score and take top technique only (avoid false combinations)
        sorted_techniques = sorted(technique_scores.items(), key=lambda x: -x[1])

        if not sorted_techniques:
            return "Analyze how the clue breaks down into definition and wordplay"

        # Return only the highest-scoring technique
        tech_name = sorted_techniques[0][0]
        return WORDPLAY_TECHNIQUES[tech_name]['hint']

    def _generate_structural_hint(self, full_text: str, paragraphs: List[str],
                                   definitions: List[str]) -> str:
        """
        Level 3: Structural breakdown - parse the explanation to extract useful info

        Instead of generic keyword matching, parse the actual explanation to find:
        - "indicated by X" patterns
        - "anagram of X" patterns
        - "X in Y" or "X around Y" structures
        - Quoted clue words and their roles
        """
        text_lower = full_text.lower()

        # Extract quoted clue references (words from the clue being explained)
        clue_refs = re.findall(r"['\"]([^'\"]+)['\"]", full_text)
        clue_refs = [ref for ref in clue_refs if len(ref) > 1 and not ref.isupper()]

        # Try to parse specific patterns from the explanation

        # Pattern 1: "indicated by 'X'" or "'X' indicates/indicating"
        indicator_match = re.search(
            r"(?:indicated\s+by|signalled\s+by|flagged\s+by)\s+['\"]([^'\"]+)['\"]",
            text_lower
        )
        if not indicator_match:
            indicator_match = re.search(
                r"['\"]([^'\"]+)['\"]\s+(?:indicates|indicating|signals|is\s+the\s+(?:anagram\s+)?indicator)",
                text_lower
            )

        indicator = indicator_match.group(1) if indicator_match else None

        # Pattern 2: "anagram of X" - find the fodder
        anagram_fodder = None
        anagram_match = re.search(r"anagram\s+of\s+['\"]?([^'\".,]+)['\"]?", text_lower)
        if anagram_match:
            anagram_fodder = anagram_match.group(1).strip()

        # Pattern 3: "X in Y" or "X around Y" for containers
        container_match = re.search(
            r"['\"]?([^'\"]+)['\"]?\s+(?:in|inside|within|around|outside|holding|containing)\s+['\"]?([^'\"]+)['\"]?",
            text_lower
        )

        # Pattern 4: "X reversed" or "reversal of X"
        reversal_match = re.search(
            r"(?:['\"]([^'\"]+)['\"]\s+reversed|reversal\s+of\s+['\"]?([^'\".,]+)['\"]?)",
            text_lower
        )

        # Pattern 5: "hidden in X" or "X contains the hidden word"
        hidden_match = re.search(
            r"(?:hidden\s+(?:in|within)\s+['\"]?([^'\".,]+)['\"]?|['\"]([^'\"]+)['\"]\s+contains)",
            text_lower
        )

        # Now build the hint based on what we found

        # Anagram with indicator and fodder
        if 'anagram' in text_lower:
            if indicator and anagram_fodder:
                return f"'{indicator}' is the anagram indicator - rearrange '{anagram_fodder}'"
            elif indicator:
                return f"'{indicator}' is the anagram indicator - find the letters to rearrange"
            elif anagram_fodder:
                return f"Rearrange the letters of '{anagram_fodder}'"
            elif clue_refs:
                return f"This is an anagram - rearrange letters from '{clue_refs[0]}'"
            return "This is an anagram - find the indicator and the letters to rearrange"

        # Hidden word
        if 'hidden' in text_lower:
            if hidden_match:
                source = hidden_match.group(1) or hidden_match.group(2)
                if source:
                    return f"The answer is hidden in the letters of '{source}'"
            if clue_refs:
                return f"The answer is hidden within '{clue_refs[0]}'"
            return "The answer is hidden within consecutive letters in the clue"

        # Reversal
        if 'reversal' in text_lower or 'reversed' in text_lower:
            if reversal_match:
                reversed_word = reversal_match.group(1) or reversal_match.group(2)
                if reversed_word:
                    return f"Write '{reversed_word}' backwards"
            if indicator:
                return f"'{indicator}' signals reversal"
            if clue_refs:
                return f"Reverse '{clue_refs[0]}' (or what it represents)"
            return "Reverse the letters of a word from the clue"

        # Container/insertion
        if any(word in text_lower for word in ['container', 'envelope', 'insertion']):
            if container_match and len(clue_refs) >= 2:
                return f"Put '{clue_refs[0]}' inside/around '{clue_refs[1]}'"
            elif len(clue_refs) >= 2:
                return f"Combine '{clue_refs[0]}' and '{clue_refs[1]}' - one goes inside the other"
            return "One part goes inside or around another"

        # Homophone
        if 'homophone' in text_lower or 'sounds like' in text_lower:
            if indicator and clue_refs:
                return f"'{indicator}' signals a homophone - '{clue_refs[0]}' sounds like the answer"
            if clue_refs:
                return f"'{clue_refs[0]}' sounds like the answer when spoken"
            return "The answer sounds like another word"

        # Double definition
        if 'double definition' in text_lower or 'two definitions' in text_lower:
            if len(definitions) >= 2:
                return f"Find a word meaning both '{definitions[0]}' and '{definitions[1]}'"
            return "Find a word with two different meanings that match the clue"

        # Charade (parts joined together)
        if any(word in text_lower for word in ['charade', 'followed by', 'plus', ' + ']):
            if len(clue_refs) >= 2:
                parts = "' + '".join(clue_refs[:3])
                return f"Join the parts: '{parts}'"
            return "Join the wordplay parts together in sequence"

        # Deletion
        if 'deletion' in text_lower or any(word in text_lower for word in ['headless', 'endless', 'heartless', 'beheaded', 'curtailed']):
            del_type = None
            if any(w in text_lower for w in ['headless', 'beheaded', 'topless']):
                del_type = "first"
            elif any(w in text_lower for w in ['endless', 'curtailed', 'docked']):
                del_type = "last"
            elif any(w in text_lower for w in ['heartless', 'gutted']):
                del_type = "middle"

            if del_type and clue_refs:
                return f"Remove the {del_type} letter from '{clue_refs[0]}'"
            elif del_type:
                return f"Remove the {del_type} letter from a word"
            elif clue_refs:
                return f"Remove letter(s) from '{clue_refs[0]}'"
            return "Remove letter(s) from a word"

        # Fallback: use the quoted clue references if we have them
        if clue_refs:
            if len(clue_refs) >= 2:
                return f"Work with '{clue_refs[0]}' and '{clue_refs[1]}'"
            return f"Focus on '{clue_refs[0]}' in the clue"

        return "Break down the clue into definition and wordplay parts"

    # Common anagram indicators - words that signal letters should be rearranged
    ANAGRAM_INDICATORS = [
        # Disorder/chaos
        'wild', 'crazy', 'mad', 'insane', 'lunatic', 'frantic', 'chaotic', 'messy',
        'untidy', 'disorderly', 'confused', 'bewildered', 'muddled', 'mixed',
        'scrambled', 'jumbled', 'tangled', 'mangled', 'garbled',
        # Damage/destruction
        'broken', 'shattered', 'smashed', 'wrecked', 'ruined', 'destroyed',
        'damaged', 'crushed', 'cracked', 'split',
        # Movement/change
        'moving', 'dancing', 'spinning', 'whirling', 'tumbling', 'rolling',
        'shifting', 'changing', 'altered', 'converted', 'transformed',
        'reformed', 'remodeled', 'revised', 'edited', 'adapted',
        # Cooking/processing
        'cooked', 'baked', 'fried', 'stewed', 'boiled', 'roasted', 'grilled',
        'stirred', 'blended', 'mashed', 'minced', 'chopped', 'diced',
        # Intoxication
        'drunk', 'tipsy', 'plastered', 'smashed', 'wasted', 'hammered', 'stoned',
        # Wrongness/error
        'wrong', 'bad', 'poor', 'faulty', 'flawed', 'mistaken', 'erroneous',
        'off', 'out', 'awry', 'amiss',
        # Construction
        'built', 'assembled', 'constructed', 'arranged', 'organized', 'sorted',
        'ordered', 'designed', 'fashioned', 'devised', 'developed',
        # Other common indicators
        'novel', 'new', 'fresh', 'different', 'unusual', 'strange', 'odd',
        'peculiar', 'curious', 'exotic', 'fancy', 'free', 'loose', 'rough',
        'crude', 'raw', 'maybe', 'perhaps', 'possibly', 'potentially',
        'could be', 'might be', 'working', 'playing', 'sporting',
    ]

    def _find_anagram_indicator(self, text: str, clue_refs: List[str]) -> Optional[str]:
        """Find the anagram indicator word in the explanation"""
        text_lower = text.lower()

        # Look for explicit "indicator is X" or "X is the anagram indicator" patterns
        indicator_pattern = re.search(
            r"['\"]([^'\"]+)['\"]\s*(?:is|as|being)\s*(?:the\s*)?(?:anagram\s*)?indicator",
            text_lower
        )
        if indicator_pattern:
            return indicator_pattern.group(1)

        # Look for "indicated by X" pattern
        indicated_by = re.search(r"indicated\s+by\s+['\"]?([^'\".,]+)['\"]?", text_lower)
        if indicated_by:
            return indicated_by.group(1).strip()

        # Search for known anagram indicators in the quoted clue references
        for ref in clue_refs:
            ref_lower = ref.lower()
            for indicator in self.ANAGRAM_INDICATORS:
                if indicator in ref_lower or ref_lower in indicator:
                    return ref

        # Search in the full text for indicator words
        for indicator in self.ANAGRAM_INDICATORS:
            # Look for the indicator as a standalone word
            if re.search(r'\b' + re.escape(indicator) + r'\b', text_lower):
                return indicator

        return None

    def _find_anagram_fodder(self, text: str, clue_refs: List[str]) -> Optional[str]:
        """Find the anagram indicator and fodder to create a helpful hint"""
        text_lower = text.lower()

        # Find the indicator
        indicator = self._find_anagram_indicator(text, clue_refs)

        # Look for "anagram of X" patterns to find fodder
        anagram_of = re.search(r'anagram\s+of\s+["\']?([^"\'.,]+)["\']?', text_lower)

        if indicator and anagram_of:
            fodder = anagram_of.group(1).strip()
            return f"'{indicator}' is the anagram indicator - rearrange '{fodder}'"
        elif indicator:
            return f"'{indicator}' is the anagram indicator - find the letters to rearrange"
        elif anagram_of:
            fodder = anagram_of.group(1).strip()
            return f"Rearrange the letters of '{fodder}'"

        # Count letters in potential fodder from quotes
        if clue_refs:
            for ref in clue_refs:
                clean = re.sub(r'[^a-zA-Z]', '', ref)
                if len(clean) >= 4:
                    return f"Rearrange letters - look for the anagram indicator in the clue"

        return None

    def _generate_full_explanation(self, paragraphs: List[str],
                                    definitions: List[str]) -> str:
        """
        Level 4: Complete explanation

        This provides the full breakdown including the ANSWER and explanation.
        Format: ANSWER: [answer] | Definition: [def] | Wordplay: [explanation]
        """
        full_text = ' '.join(paragraphs)
        parts = []

        # Extract the answer (longest ALL CAPS word, usually the answer)
        caps_words = re.findall(r'\b[A-Z]{2,}\b', full_text)
        if caps_words:
            # The answer is typically the longest caps word, or appears at the end
            # Filter out common non-answer caps like "I", "A", abbreviations
            answer_candidates = [w for w in caps_words if len(w) >= 3]
            if answer_candidates:
                # Prefer the longest one, or the last one if tied
                answer = max(answer_candidates, key=len)
                parts.append(f"Answer: {answer}")

        # Definition section
        if definitions:
            if len(definitions) == 1:
                parts.append(f"Definition: '{definitions[0]}'")
            else:
                parts.append(f"Definitions: '{definitions[0]}' and '{definitions[1]}'")

        # Wordplay explanation - use the main content paragraphs
        if paragraphs:
            # Find the most explanatory paragraph (usually has the CAPS answer parts)
            best_para = None
            best_score = 0

            for para in paragraphs:
                # Score by presence of caps words and structural words
                caps_count = len(re.findall(r'\b[A-Z]{2,}\b', para))
                has_structure = any(word in para.lower() for word in
                                   ['plus', 'in', 'around', 'gives', 'makes', '=', '+'])
                score = caps_count + (2 if has_structure else 0)

                if score > best_score:
                    best_score = score
                    best_para = para

            if best_para:
                explanation = best_para.strip()
                # Don't duplicate if it's the same as definition
                if not definitions or explanation.lower() != definitions[0].lower():
                    parts.append(f"Wordplay: {explanation}")

        if not parts:
            return ' '.join(paragraphs) if paragraphs else "No explanation available."

        return " | ".join(parts)


# For backward compatibility
class HintGenerator:
    """Legacy class that uses enhanced generator"""

    def __init__(self):
        self.enhanced = EnhancedHintGenerator()

    @staticmethod
    def generate_hints(hint_paragraphs: List[str]) -> List[str]:
        """Generate hints using enhanced system"""
        generator = EnhancedHintGenerator()
        return generator.generate_hints(hint_paragraphs, author='generic')
