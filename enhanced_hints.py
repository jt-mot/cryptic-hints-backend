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
        'hint': "This clue involves reversing letters or a word",
        'partial': "Write something backwards"
    },
    'container': {
        'keywords': ['container', 'envelope', 'around', 'outside', 'wrapping', 'holding',
                     'embracing', 'clutching', 'grasping', 'containing', 'swallowing',
                     'surrounding', 'boxing', 'circling'],
        'hint': "One part of the answer goes around or inside another",
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
        'hint': "The answer sounds like another word or phrase",
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
        'hint': "Remove a letter or letters from a word",
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
        Level 1: Help locate the definition

        The definition is the "straight" part of the clue that directly means the answer.
        This hint should help the solver identify which part of the clue is the definition
        without giving away the answer.
        """
        # Use extracted HTML definitions (underlined text) - most reliable
        if definitions:
            # Check position - definitions are usually at start or end
            first_def = definitions[0]

            # Don't reveal the definition directly, hint at its location
            if len(definitions) == 1:
                # Try to determine if it's at start or end
                if paragraphs and paragraphs[0]:
                    first_para = paragraphs[0].lower()
                    def_lower = first_def.lower()

                    # Check relative position
                    def_pos = first_para.find(def_lower)
                    if def_pos != -1:
                        para_len = len(first_para)
                        if def_pos < para_len * 0.3:
                            return "The definition is at the beginning of the clue"
                        elif def_pos > para_len * 0.7:
                            return "The definition is at the end of the clue"

                return f"Look for a {len(first_def.split())}-word definition"
            else:
                return "This clue has a double definition - both parts define the answer"

        # Check for explicit definition indicators in the text
        def_patterns = [
            (r'definition[:\s]+["\']?([^"\'.,]+)["\']?', "definition"),
            (r'def\.?[:\s]+["\']?([^"\'.,]+)["\']?', "definition"),
            (r'meaning[:\s]+["\']?([^"\'.,]+)["\']?', "meaning"),
        ]

        for pattern, indicator in def_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                def_text = match.group(1).strip()
                word_count = len(def_text.split())
                if word_count <= 3:
                    return f"The {indicator} is a {word_count}-word phrase"
                else:
                    return f"Look for the {indicator} - it's a longer phrase"

        # Check for double definition clues
        if 'double definition' in full_text.lower() or 'two definitions' in full_text.lower():
            return "This is a double definition - find a word with two meanings"

        # Analyze clue structure from first paragraph
        if paragraphs:
            first_para = paragraphs[0]
            # Count quoted segments
            quoted = re.findall(r"['\"]([^'\"]+)['\"]", first_para)
            if len(quoted) >= 2:
                return "The definition is one of the quoted phrases in the clue"
            elif len(quoted) == 1:
                return "Pay attention to the quoted phrase"

        # Default based on common patterns
        return "The definition is usually at the start or end of the clue"

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
        Level 3: Structural breakdown without revealing the answer

        This should show HOW the wordplay works without giving away the actual
        answer components. Focus on the clue's structure and mechanics.
        """
        text_lower = full_text.lower()

        # Extract quoted clue references (words from the clue)
        clue_refs = re.findall(r"['\"]([^'\"]+)['\"]", full_text)
        clue_refs = [ref for ref in clue_refs if len(ref) > 1 and not ref.isupper()]

        # Identify answer components (ALL CAPS words) - we'll hide these
        answer_parts = re.findall(r'\b[A-Z]{2,}\b', full_text)

        # Determine the structure based on technique
        technique_scores = {}
        for tech_name, tech_info in WORDPLAY_TECHNIQUES.items():
            score = sum(1 for kw in tech_info['keywords'] if kw in text_lower)
            if score > 0:
                technique_scores[tech_name] = score

        if not technique_scores:
            if clue_refs:
                return f"Work with these clue elements: '{', '.join(clue_refs[:3])}'"
            return "Break down each component of the clue and combine them"

        primary_technique = max(technique_scores.items(), key=lambda x: x[1])[0]

        # Generate technique-specific structural hint
        if primary_technique == 'anagram':
            # Find anagram fodder indicators
            fodder_hint = self._find_anagram_fodder(full_text, clue_refs)
            if fodder_hint:
                return fodder_hint
            return "Find the anagram indicator and identify which letters to rearrange"

        elif primary_technique == 'hidden':
            if clue_refs:
                return f"The answer is hidden within consecutive letters in '{clue_refs[0]}...'"
            return "Scan through the clue text for the answer hidden within"

        elif primary_technique == 'reversal':
            if clue_refs:
                return f"Reverse the letters of something related to '{clue_refs[0]}'"
            return "Find what needs to be reversed and write it backwards"

        elif primary_technique in ('container', 'insertion'):
            if len(clue_refs) >= 2:
                return f"One part (from '{clue_refs[0]}') goes inside/around another (from '{clue_refs[1]}')"
            return "Identify the outer and inner components, then nest them"

        elif primary_technique == 'charade':
            if clue_refs:
                parts = clue_refs[:3]
                return f"Chain together parts from: '{', '.join(parts)}'"
            return "Join the wordplay components in sequence"

        elif primary_technique == 'deletion':
            if clue_refs:
                return f"Remove letter(s) from something related to '{clue_refs[0]}'"
            return "Find what to remove from which word"

        elif primary_technique == 'homophone':
            return "The answer sounds like another word - say it out loud"

        elif primary_technique == 'abbreviation' or primary_technique == 'initial_letters':
            return "Look for standard abbreviations or take initial letters"

        elif primary_technique == 'double_definition':
            return "Find a single word that matches both definitions in the clue"

        else:
            # Fallback with clue references
            if clue_refs:
                return f"The wordplay involves: '{', '.join(clue_refs[:2])}'"
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
