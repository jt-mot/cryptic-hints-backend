"""
Enhanced Hint Generation System

Handles different fifteensquared author styles and produces better progressive hints
"""

import re
from typing import List, Dict, Optional


class AuthorStyleDetector:
    """Detects the author/style of fifteensquared analysis"""
    
    @staticmethod
    def detect_author(url: str, content: str) -> str:
        """
        Detect the author from URL or content
        
        Returns author name or 'generic'
        """
        # Check content for "by AuthorName" pattern (most reliable)
        # Pattern: "at 2:29 am by PeterO" or "posted by PeterO"
        content_lower = content.lower()
        
        # Look for "by [author]" pattern
        by_match = re.search(r'(?:at|posted)\s+.*?\s+by\s+([a-z]+)', content_lower, re.IGNORECASE)
        if by_match:
            author = by_match.group(1).lower()
            # Map known authors
            known_authors = ['petero', 'verlaine', 'vinyl', 'pommers', 'jackkt', 
                           'bertandjoyce', 'alankd', 'cornick']
            if author in known_authors:
                return author
        
        # Fallback: check for author name anywhere in content
        if 'petero' in content_lower:
            return 'petero'
        elif 'verlaine' in content_lower:
            return 'verlaine'
        elif 'vinyl' in content_lower:
            return 'vinyl'
        
        # Check URL for author name
        url_lower = url.lower()
        authors = ['petero', 'verlaine', 'vinyl', 'pommers', 'jackkt', 
                   'bertandjoyce', 'alankd', 'cornick']
        
        for author in authors:
            if author in url_lower:
                return author
        
        return 'generic'
        
        return 'generic'


class EnhancedHintGenerator:
    """Generate progressive hints with author-aware parsing"""
    
    def __init__(self):
        self.style_detector = AuthorStyleDetector()
    
    def generate_hints(self, hint_paragraphs: List[str], author: str = 'generic', definitions: List[str] = None) -> List[str]:
        """
        Generate 4-level progressive hints based on author style
        
        Args:
            hint_paragraphs: Raw text paragraphs from analysis
            author: Author name (petero, verlaine, etc.)
            definitions: Extracted HTML definitions (underlined/italicized text)
            
        Returns:
            List of 4 hints
        """
        if not hint_paragraphs:
            return ['', '', '', '']
        
        if definitions is None:
            definitions = []
        
        # Choose parsing strategy based on author
        if author == 'petero':
            return self._generate_petero_style(hint_paragraphs, definitions)
        elif author == 'verlaine':
            return self._generate_verlaine_style(hint_paragraphs, definitions)
        else:
            return self._generate_generic_style(hint_paragraphs, definitions)
    
    def _generate_petero_style(self, paragraphs: List[str], definitions: List[str]) -> List[str]:
        """
        PeterO style:
        - Often starts with clue text in parentheses
        - Breaks down wordplay systematically
        - Usually has clear definition indicator
        
        Example format:
        "Don't be cruel to old comedian, simple at heart (2,4,2)"
        "An envelope ('at heart') of EASY ('simple') in GOON ('old comedian')."
        """
        hints = ['', '', '', '']
        full_text = ' '.join(paragraphs)
        
        # Level 1: Use extracted HTML definitions (underlined/italicized)
        if definitions:
            # PeterO underlines definitions - use the first one found
            hints[0] = f"Definition: {definitions[0]}"
        else:
            # Fallback to text-based extraction
            def_patterns = [
                r'definition[:\s]+([^.]+)',
                r'def[:\s]+([^.]+)',
                r"'([^']+)'\s+(?:is|means|=)",
            ]
            
            for pattern in def_patterns:
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    hints[0] = f"Look for the definition: {match.group(1).strip()}"
                    break
            
            if not hints[0]:
                # Last resort: look for quoted words
                if paragraphs:
                    quoted = re.findall(r"'([^']+)'", paragraphs[0])
                    if quoted:
                        hints[0] = f"The definition might be: {quoted[0]}"
                    else:
                        hints[0] = "Look for the definition in the clue."
        
        # Level 2: Wordplay type
        wordplay_indicators = {
            'anagram': ['anagram', 'mixed', 'confused', 'scrambled', 'rearranged'],
            'hidden': ['hidden', 'in', 'concealed', 'some of'],
            'reversal': ['reversal', 'back', 'returned', 'going up'],
            'charade': ['charade', 'followed by', 'after', 'before'],
            'container': ['container', 'around', 'outside', 'inside', 'envelope'],
            'homophone': ['sounds like', 'homophone', 'we hear', 'on the radio'],
            'double_def': ['double definition', 'two definitions'],
        }
        
        for wp_type, indicators in wordplay_indicators.items():
            if any(ind in full_text.lower() for ind in indicators):
                type_descriptions = {
                    'anagram': 'This involves an anagram.',
                    'hidden': 'The answer is hidden within the clue.',
                    'reversal': 'This involves a reversal.',
                    'charade': 'This is a charade - join parts together.',
                    'container': 'This is a container clue - one part goes inside another.',
                    'homophone': 'This is a homophone - it sounds like something.',
                    'double_def': 'This is a double definition.',
                }
                hints[1] = type_descriptions.get(wp_type, 'Look at how the clue breaks down.')
                break
        
        if not hints[1]:
            hints[1] = "Think about how the words in the clue might break down."
        
        # Level 3: Partial breakdown
        # Extract key wordplay components
        if len(paragraphs) > 1:
            # Take second paragraph but remove the answer if mentioned
            partial = paragraphs[1]
            # Remove anything that looks like the full answer in caps
            partial = re.sub(r'\b[A-Z]{5,}\b', '[ANSWER]', partial)
            hints[2] = partial[:300]
        else:
            # Extract component explanations
            components = re.findall(r"'([^']+)'\s+\(([^)]+)\)", full_text)
            if components and len(components) >= 2:
                hints[2] = f"Break it down: '{components[0][0]}' means {components[0][1]}, and '{components[1][0]}' means {components[1][1]}."
            else:
                hints[2] = full_text[:300]
        
        # Level 4: Full explanation
        hints[3] = full_text
        
        return hints
    
    def _generate_verlaine_style(self, paragraphs: List[str], definitions: List[str]) -> List[str]:
        """
        Verlaine style:
        - Often more conversational
        - May include cultural references
        - Good at explaining wordplay steps
        """
        hints = ['', '', '', '']
        full_text = ' '.join(paragraphs)
        
        # Similar structure but different tone
        hints[0] = self._extract_definition_hint(full_text, paragraphs)
        hints[1] = self._extract_wordplay_type(full_text)
        hints[2] = paragraphs[1][:300] if len(paragraphs) > 1 else full_text[:300]
        hints[3] = full_text
        
        return hints
    
    def _generate_generic_style(self, paragraphs: List[str], definitions: List[str]) -> List[str]:
        """
        Generic fallback for unknown authors
        Uses conservative extraction
        """
        hints = ['', '', '', '']
        full_text = ' '.join(paragraphs)
        
        # Level 1: Try to find definition
        hints[0] = self._extract_definition_hint(full_text, paragraphs)
        
        # Level 2: Wordplay type
        hints[1] = self._extract_wordplay_type(full_text)
        
        # Level 3: Middle content
        if len(paragraphs) > 1:
            hints[2] = paragraphs[1][:250]
        else:
            sentences = re.split(r'[.!?]+', full_text)
            if len(sentences) >= 3:
                hints[2] = '. '.join(sentences[1:3]) + '.'
            else:
                hints[2] = full_text[:250]
        
        # Level 4: Full text
        hints[3] = full_text
        
        return hints
    
    def _extract_definition_hint(self, text: str, paragraphs: List[str]) -> str:
        """Extract or infer the definition hint"""
        # Look for explicit definition mention
        def_match = re.search(r'definition[:\s]+([^.]+)', text, re.IGNORECASE)
        if def_match:
            return f"Definition: {def_match.group(1).strip()}"
        
        # Look for quoted definition
        quoted = re.findall(r"'([^']+)'", paragraphs[0] if paragraphs else text)
        if quoted and len(quoted[0]) > 3:
            return f"The definition is likely '{quoted[0]}'"
        
        # Fall back to first sentence
        sentences = re.split(r'[.!?]+', text)
        if sentences:
            first = sentences[0].strip()
            if len(first) > 10 and len(first) < 100:
                return first + '.'
        
        return "Look for the definition in the clue."
    
    def _extract_wordplay_type(self, text: str) -> str:
        """Detect wordplay type from text"""
        text_lower = text.lower()
        
        wordplay_map = [
            (['anagram', 'mixed', 'confused', 'scrambled'], 'This is an anagram.'),
            (['hidden', 'concealed', 'some of'], 'The answer is hidden in the clue.'),
            (['reversal', 'back', 'returned'], 'This involves a reversal.'),
            (['container', 'around', 'outside', 'envelope'], 'One part contains another.'),
            (['sounds like', 'homophone', 'we hear'], 'This is a homophone.'),
            (['double definition'], 'This is a double definition.'),
            (['charade', 'followed by'], 'Join the parts together.'),
        ]
        
        for keywords, description in wordplay_map:
            if any(kw in text_lower for kw in keywords):
                return description
        
        return "Think about how the clue breaks down into parts."


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
