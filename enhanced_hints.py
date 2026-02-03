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
        
        # Level 2: Extract wordplay technique using AI
        if len(paragraphs) > 1:
            wordplay_explanation = paragraphs[1]
            
            # Use AI to extract just the technique
            hints[1] = self._extract_wordplay_technique(wordplay_explanation)
        else:
            # Fallback: try to detect wordplay type if no second paragraph
            hints[1] = self._detect_wordplay_fallback(full_text)
        
        # Level 3: Partial wordplay hints without revealing the answer
        # Extract clue references (words in quotes) but hide the answer parts (all caps)
        if len(paragraphs) > 1:
            hints[2] = self._create_partial_hint(paragraphs[1])
        else:
            hints[2] = "Break down the clue into its component parts"
        
        # Level 4: Full explanation with wordplay mechanics
        hints[3] = self._create_full_explanation(paragraphs, definitions)
        
        return hints
    
    def _create_partial_hint(self, wordplay_text: str) -> str:
        """
        Create a Level 3 hint that's helpful but doesn't give away the answer
        
        Strategy:
        - Keep clue references (text in quotes after words like 'simple', 'old comedian')
        - Remove or mask answer components (words in all caps like EASY, GOON)
        - Keep structural words (in, inside, around, after, etc.)
        """
        # Remove answer components (all-caps words)
        hint = re.sub(r'\b[A-Z]{2,}\b', '[...]', wordplay_text)
        
        # Extract the clue references to highlight
        clue_refs = re.findall(r"'([^']+)'", hint)
        
        if len(clue_refs) >= 2:
            # Build a helpful hint
            if 'envelope' in hint.lower() or 'container' in hint.lower() or 'in' in hint.lower() or 'inside' in hint.lower():
                return f"Put '{clue_refs[0]}' inside '{clue_refs[1]}' (or vice versa)"
            elif 'after' in hint.lower() or 'before' in hint.lower() or 'then' in hint.lower():
                return f"Join '{clue_refs[0]}' and '{clue_refs[1]}' together"
            elif 'reversal' in hint.lower() or 'back' in hint.lower():
                return f"Reverse '{clue_refs[0]}' or '{clue_refs[1]}'"
            else:
                # Generic hint showing clue components
                refs_str = "', '".join(clue_refs[:3])
                return f"The wordplay uses: '{refs_str}'"
        elif len(clue_refs) == 1:
            return f"Focus on '{clue_refs[0]}' in the clue"
        else:
            # No quotes found, just clean up the all-caps
            return hint[:200].strip()
    
    def _create_full_explanation(self, paragraphs: List[str], definitions: List[str]) -> str:
        """
        Create a complete Level 4 explanation
        
        Should include:
        - The definition
        - The complete wordplay breakdown
        - How it all fits together
        """
        parts = []
        
        # Start with definition
        if definitions:
            parts.append(f"Definition: '{definitions[0]}'")
        
        # Add full wordplay explanation
        if len(paragraphs) > 1:
            # Clean up but keep the full explanation
            wordplay = paragraphs[1]
            parts.append(f"Wordplay: {wordplay}")
        
        # Add any additional notes from later paragraphs
        if len(paragraphs) > 2:
            notes = ' '.join(paragraphs[2:])
            if notes and len(notes) > 10:
                parts.append(notes)
        
        return ' '.join(parts)
    
    def _extract_wordplay_technique(self, explanation: str) -> str:
        """
        Use AI to extract the cryptic technique and format as a helpful hint
        
        Examples:
        "An anagram of LATE" -> "This clue uses an anagram indicator"
        "A reversal of DOG in CAT" -> "This clue uses a reversal inside a container"
        "Two definitions" -> "This is a double definition clue"
        """
        try:
            import requests
            import json
            
            prompt = f"""You are helping someone solve a cryptic crossword. Based on this explanation of how the clue works, write a friendly hint that tells them what technique to look for, without giving away the answer.

Explanation: {explanation}

Write a single sentence hint that:
- Starts with "This clue uses..." or "Look for..." or "This is..."
- Mentions the cryptic technique (anagram, hidden word, reversal, container, charade, homophone, double definition, etc.)
- Is encouraging and helpful
- Does NOT include any part of the answer
- Is maximum 15 words

Examples:
"This clue uses an anagram indicator"
"Look for a hidden word in the clue"
"This is a container clue - one word goes inside another"
"This clue uses a reversal plus a charade"
"Look for two separate definitions of the same word"
"""
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json"},
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 100,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('content'):
                    technique = data['content'][0].get('text', '').strip()
                    if technique and len(technique) < 150:
                        return technique
        except Exception as e:
            # If AI fails, fall back to keyword detection
            print(f"      AI technique extraction failed: {e}")
        
        # Fallback to keyword detection
        return self._detect_wordplay_fallback(explanation)
    
    def _detect_wordplay_fallback(self, text: str) -> str:
        """Fallback keyword-based detection with friendly phrasing"""
        text_lower = text.lower()
        
        techniques = []
        if 'anagram' in text_lower or 'mixed' in text_lower or 'confused' in text_lower:
            techniques.append('an anagram')
        if 'hidden' in text_lower or 'concealed' in text_lower:
            techniques.append('a hidden word')
        if 'reversal' in text_lower or 'back' in text_lower or 'reversed' in text_lower:
            techniques.append('a reversal')
        if 'container' in text_lower or 'envelope' in text_lower or 'around' in text_lower or 'inside' in text_lower:
            techniques.append('a container')
        if 'sounds like' in text_lower or 'homophone' in text_lower:
            techniques.append('a homophone')
        if 'double definition' in text_lower:
            return "This is a double definition clue"
        
        if len(techniques) == 1:
            return f"This clue uses {techniques[0]}"
        elif len(techniques) == 2:
            return f"This clue uses {techniques[0]} and {techniques[1]}"
        elif len(techniques) > 2:
            return f"This clue combines {', '.join(techniques[:-1])} and {techniques[-1]}"
        else:
            return "Look at how the clue breaks down into parts"
    
    def _generate_verlaine_style(self, paragraphs: List[str], definitions: List[str]) -> List[str]:
        """
        Verlaine style:
        - Often more conversational
        - May include cultural references
        - Good at explaining wordplay steps
        """
        hints = ['', '', '', '']
        full_text = ' '.join(paragraphs)
        
        # Use same improved structure as generic
        hints[0] = self._extract_definition_hint(full_text, paragraphs, definitions)
        hints[1] = self._detect_wordplay_fallback(full_text)
        
        if len(paragraphs) > 1:
            hints[2] = self._create_partial_hint(paragraphs[1])
        else:
            hints[2] = "Look at how the different parts of the clue combine"
        
        hints[3] = self._create_full_explanation(paragraphs, definitions)
        
        return hints
    
    def _generate_generic_style(self, paragraphs: List[str], definitions: List[str]) -> List[str]:
        """
        Generic fallback for unknown authors
        Uses conservative extraction with improved hints
        """
        hints = ['', '', '', '']
        full_text = ' '.join(paragraphs)
        
        # Level 1: Try to find definition
        hints[0] = self._extract_definition_hint(full_text, paragraphs, definitions)
        
        # Level 2: Wordplay type (use friendly detection)
        hints[1] = self._detect_wordplay_fallback(full_text)
        
        # Level 3: Partial hint without giving away answer
        if len(paragraphs) > 1:
            hints[2] = self._create_partial_hint(paragraphs[1])
        else:
            # Extract middle sentences without caps
            cleaned = re.sub(r'\b[A-Z]{2,}\b', '[...]', full_text)
            sentences = re.split(r'[.!?]+', cleaned)
            if len(sentences) >= 2:
                hints[2] = sentences[1].strip() + '.'
            else:
                hints[2] = "Look at how the different parts of the clue work together"
        
        # Level 4: Full explanation
        hints[3] = self._create_full_explanation(paragraphs, definitions)
        
        return hints
    
    def _extract_definition_hint(self, text: str, paragraphs: List[str], definitions: List[str] = None) -> str:
        """Extract or infer the definition hint"""
        # Use extracted HTML definitions first
        if definitions:
            return f"Definition: {definitions[0]}"
        
        # Look for explicit definition mention
        def_match = re.search(r'definition[:\s]+([^.]+)', text, re.IGNORECASE)
        if def_match:
            return f"Definition: {def_match.group(1).strip()}"
        
        # Look for quoted definition
        quoted = re.findall(r"'([^']+)'", paragraphs[0] if paragraphs else text)
        if quoted and len(quoted[0]) > 3:
            return f"The definition is likely '{quoted[0]}'"
        
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
