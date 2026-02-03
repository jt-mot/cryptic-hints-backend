"""
Enhanced Hint Generation System

Handles different fifteensquared author styles and produces better progressive hints
"""

import re
from typing import List, Dict, Optional, Tuple


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
    """Generate progressive hints with author-aware parsing"""

    def __init__(self):
        self.style_detector = AuthorStyleDetector()

    def generate_hints(self, hint_paragraphs: List[str], author: str = 'generic',
                       definitions: List[str] = None) -> List[str]:
        """
        Generate 4-level progressive hints based on author style

        Hint Levels:
        - Level 1: Definition location/hint (gentle nudge)
        - Level 2: Wordplay technique identification (what type of clue)
        - Level 3: Structural breakdown without answer (how to construct)
        - Level 4: Full explanation (complete solution)

        Args:
            hint_paragraphs: Raw text paragraphs from analysis
            author: Author name (petero, verlaine, etc.)
            definitions: Extracted HTML definitions (underlined/italicized text)

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

        # Generate each hint level
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
        detected_techniques = []

        # Score each technique by keyword matches
        technique_scores: Dict[str, int] = {}
        for tech_name, tech_info in WORDPLAY_TECHNIQUES.items():
            score = 0
            for keyword in tech_info['keywords']:
                if keyword in text_lower:
                    # Weight multi-word keywords higher
                    score += len(keyword.split())
            if score > 0:
                technique_scores[tech_name] = score

        # Sort by score and take top techniques
        sorted_techniques = sorted(technique_scores.items(), key=lambda x: -x[1])

        if not sorted_techniques:
            return "Analyze how the clue breaks down into definition and wordplay"

        # Build hint based on detected techniques
        top_techniques = sorted_techniques[:2]  # Max 2 techniques to mention

        if len(top_techniques) == 1:
            tech_name = top_techniques[0][0]
            return WORDPLAY_TECHNIQUES[tech_name]['hint']
        else:
            # Multiple techniques - likely a compound clue
            tech_names = [t[0] for t in top_techniques]
            hints = [WORDPLAY_TECHNIQUES[t]['hint'].split(' - ')[0] for t in tech_names]

            # Create combined hint
            if 'charade' in tech_names:
                other = [h for t, h in zip(tech_names, hints) if t != 'charade'][0]
                return f"This combines a charade with {tech_names[0] if tech_names[0] != 'charade' else tech_names[1]} - parts join together"
            else:
                return f"This clue combines {tech_names[0].replace('_', ' ')} and {tech_names[1].replace('_', ' ')}"

    def _generate_structural_hint(self, full_text: str, paragraphs: List[str],
                                   definitions: List[str]) -> str:
        """
        Level 3: Structural breakdown - more revealing hint

        This should give a clearer picture of how the wordplay works,
        showing the components from the clue without the final answer.
        """
        text_lower = full_text.lower()

        # Extract quoted clue references (words from the clue being explained)
        clue_refs = re.findall(r"['\"]([^'\"]+)['\"]", full_text)
        clue_refs = [ref for ref in clue_refs if len(ref) > 1 and not ref.isupper()]

        # Identify answer components (ALL CAPS words) - we'll reference but not fully reveal
        answer_parts = re.findall(r'\b[A-Z]{2,}\b', full_text)

        # Determine the structure based on technique
        technique_scores = {}
        for tech_name, tech_info in WORDPLAY_TECHNIQUES.items():
            score = sum(1 for kw in tech_info['keywords'] if kw in text_lower)
            if score > 0:
                technique_scores[tech_name] = score

        # Build a useful hint from the explanation text
        # Look for patterns like "X gives Y" or "X = Y" without showing CAPS answers
        structural_patterns = [
            (r"['\"]([^'\"]+)['\"]\s*(?:gives|=|means|is)\s*[A-Z]+", "'{0}' leads to part of the answer"),
            (r"([a-z]+)\s+(?:in|around|inside|outside)\s+([a-z]+)", "Put '{0}' {1} '{2}'"),
        ]

        if not technique_scores:
            if clue_refs:
                return f"Work with these clue elements: '{', '.join(clue_refs[:3])}'"
            return "Break down each component of the clue and combine them"

        primary_technique = max(technique_scores.items(), key=lambda x: x[1])[0]

        # Generate technique-specific structural hint with more detail
        if primary_technique == 'anagram':
            fodder_hint = self._find_anagram_fodder(full_text, clue_refs)
            if fodder_hint:
                return fodder_hint
            if clue_refs:
                return f"Rearrange the letters from '{clue_refs[0]}'"
            return "Find the anagram indicator and rearrange those letters"

        elif primary_technique == 'hidden':
            if clue_refs:
                return f"Look for the answer hidden in the letters of '{clue_refs[0]}'"
            return "The answer is spelled out within consecutive letters in the clue"

        elif primary_technique == 'reversal':
            if clue_refs:
                return f"Write '{clue_refs[0]}' (or what it represents) backwards"
            return "Reverse the letters of the indicated word"

        elif primary_technique in ('container', 'insertion'):
            if len(clue_refs) >= 2:
                return f"'{clue_refs[0]}' goes inside or around '{clue_refs[1]}' (or vice versa)"
            elif len(clue_refs) == 1:
                return f"One part goes inside '{clue_refs[0]}' or '{clue_refs[0]}' goes inside another part"
            return "One component wraps around or goes inside another"

        elif primary_technique == 'charade':
            if len(clue_refs) >= 2:
                return f"Join: '{clue_refs[0]}' + '{clue_refs[1]}'" + (f" + '{clue_refs[2]}'" if len(clue_refs) > 2 else "")
            elif len(clue_refs) == 1:
                return f"'{clue_refs[0]}' combines with another part"
            return "Chain the wordplay components together left to right"

        elif primary_technique == 'deletion':
            # Be more specific about what kind of deletion
            if 'headless' in text_lower or 'beheaded' in text_lower:
                if clue_refs:
                    return f"Remove the first letter from '{clue_refs[0]}'"
                return "Remove the first letter from a word"
            elif 'endless' in text_lower or 'curtailed' in text_lower:
                if clue_refs:
                    return f"Remove the last letter from '{clue_refs[0]}'"
                return "Remove the last letter from a word"
            elif 'heartless' in text_lower:
                if clue_refs:
                    return f"Remove the middle letter(s) from '{clue_refs[0]}'"
                return "Remove the middle letter(s) from a word"
            else:
                if clue_refs:
                    return f"Remove a letter from '{clue_refs[0]}'"
                return "Remove the indicated letter(s) from a word"

        elif primary_technique == 'homophone':
            if clue_refs:
                return f"'{clue_refs[0]}' sounds like the answer when spoken aloud"
            return "Say the indicated word aloud - it sounds like the answer"

        elif primary_technique == 'abbreviation':
            if clue_refs:
                return f"'{clue_refs[0]}' has a standard abbreviation"
            return "Use the standard abbreviation for the indicated word"

        elif primary_technique == 'initial_letters':
            if clue_refs:
                return f"Take the first letters from '{clue_refs[0]}'"
            return "Take the initial letters of the indicated words"

        elif primary_technique == 'double_definition':
            if len(definitions) >= 2:
                return f"One word means both '{definitions[0]}' and '{definitions[1]}'"
            return "Find a word that satisfies both meanings in the clue"

        else:
            if clue_refs:
                return f"The wordplay uses: '{', '.join(clue_refs[:3])}'"
            return WORDPLAY_TECHNIQUES[primary_technique]['partial']

    def _find_anagram_fodder(self, text: str, clue_refs: List[str]) -> Optional[str]:
        """Find and describe the anagram fodder without revealing the answer"""
        text_lower = text.lower()

        # Look for "anagram of X" patterns
        anagram_of = re.search(r'anagram\s+of\s+["\']?([^"\'.,]+)["\']?', text_lower)
        if anagram_of:
            fodder = anagram_of.group(1).strip()
            letter_count = len(re.sub(r'[^a-z]', '', fodder.lower()))
            if letter_count > 0:
                return f"Find a {letter_count}-letter anagram (look for the indicator word)"

        # Count letters in potential fodder from quotes
        if clue_refs:
            for ref in clue_refs:
                clean = re.sub(r'[^a-zA-Z]', '', ref)
                if len(clean) >= 4:
                    return f"Rearrange letters - the fodder has {len(clean)} letters"

        return None

    def _generate_full_explanation(self, paragraphs: List[str],
                                    definitions: List[str]) -> str:
        """
        Level 4: Complete explanation

        This provides the full breakdown including the answer components.
        Format it clearly with definition and wordplay separated.
        """
        parts = []

        # Definition section
        if definitions:
            if len(definitions) == 1:
                parts.append(f"Definition: '{definitions[0]}'")
            else:
                parts.append(f"Definitions: {', '.join([f'\"{d}\"' for d in definitions])}")

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
                # Clean up the explanation
                explanation = best_para.strip()

                # Don't duplicate if it's the same as definition
                if definitions and explanation.lower() != definitions[0].lower():
                    parts.append(f"Wordplay: {explanation}")

            # Add any additional context from other paragraphs
            additional = []
            for para in paragraphs:
                if para != best_para and len(para) > 20:
                    # Check if it adds new information
                    if any(phrase in para.lower() for phrase in
                          ['also', 'note', 'reference', 'allusion', 'meaning']):
                        additional.append(para.strip())

            if additional:
                parts.append("Notes: " + " ".join(additional[:2]))

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
