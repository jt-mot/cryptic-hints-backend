"""
Guardian Cryptic Puzzle Scraper

Fetches puzzles from Guardian and extracts hints from fifteensquared.net
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from typing import Dict, List, Optional


class GuardianScraper:
    """Scrapes puzzle data from Guardian website"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch_puzzle(self, puzzle_number: str) -> Optional[Dict]:
        """
        Fetch puzzle from Guardian website
        
        Args:
            puzzle_number: Guardian puzzle number (e.g., "29915")
            
        Returns:
            Dict with puzzle data or None if failed
        """
        url = f"https://www.theguardian.com/crosswords/cryptic/{puzzle_number}"
        
        try:
            print(f"Fetching Guardian puzzle {puzzle_number}...")
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find the gu-island component with crossword data
            island = soup.find('gu-island', attrs={'name': 'CrosswordComponent'})
            
            if not island:
                return {'error': 'Could not find crossword data on page'}
            
            props_json = island.get('props')
            if not props_json:
                return {'error': 'No props attribute found'}
            
            # Parse JSON data
            props = json.loads(props_json)
            puzzle_data = props.get('data', {})
            
            # Extract puzzle metadata
            result = {
                'publication': 'Guardian',
                'puzzle_number': str(puzzle_data.get('number', puzzle_number)),
                'setter': puzzle_data.get('creator', {}).get('name', 'Unknown'),
                'date': self._parse_date(puzzle_data.get('date')),
                'clues': []
            }
            
            # Extract clues
            for entry in puzzle_data.get('entries', []):
                clue = {
                    'clue_number': str(entry.get('number', '')),
                    'direction': entry.get('direction', 'across'),
                    'clue_text': entry.get('clue', ''),
                    'answer': entry.get('solution', ''),
                    'enumeration': self._format_enumeration(entry.get('length'), 
                                                           entry.get('separatorLocations', {}))
                }
                result['clues'].append(clue)
            
            print(f"✓ Successfully fetched {len(result['clues'])} clues")
            return result
            
        except Exception as e:
            print(f"Error fetching Guardian puzzle: {e}")
            return {'error': str(e)}
    
    def _parse_date(self, timestamp) -> str:
        """Convert timestamp to YYYY-MM-DD format"""
        if timestamp:
            try:
                dt = datetime.fromtimestamp(timestamp / 1000)
                return dt.strftime('%Y-%m-%d')
            except:
                pass
        return datetime.now().strftime('%Y-%m-%d')
    
    def _format_enumeration(self, length, separators) -> str:
        """Format enumeration like (7) or (3,4) or (1-5)"""
        if not separators:
            return str(length)
        
        # separators is a dict like {",": [3]} or {"-": [1]}
        # This means the answer has parts
        # For now, just return the total length
        # A more complete implementation would parse the separator positions
        return str(length)


class FifteensquaredScraper:
    """Scrapes hint analysis from fifteensquared.net"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def find_puzzle_post(self, puzzle_number: str) -> Optional[str]:
        """
        Search for puzzle analysis post
        
        Returns:
            URL of the post or None
        """
        search_url = f"https://fifteensquared.net/?s=guardian+{puzzle_number}"
        
        try:
            print(f"Searching fifteensquared for Guardian {puzzle_number}...")
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for article links containing the puzzle number
            articles = soup.find_all('article')
            
            for article in articles:
                # Find title link
                title_elem = article.find(['h2', 'h1'], class_=lambda x: x and 'entry-title' in x)
                if title_elem:
                    link = title_elem.find('a', href=True)
                    if link and puzzle_number in link['href']:
                        print(f"✓ Found post: {link['href']}")
                        return link['href']
            
            # Alternative: look for any link with puzzle number
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                if f'guardian-{puzzle_number}' in href.lower():
                    print(f"✓ Found post: {href}")
                    return href
            
            print("✗ No fifteensquared post found")
            return None
            
        except Exception as e:
            print(f"Error searching fifteensquared: {e}")
            return None
    
    def fetch_hints(self, url: str) -> Dict[str, List[str]]:
        """
        Fetch and parse hint analysis from a fifteensquared post
        
        Returns:
            Dict mapping clue_id to list of hint paragraphs
        """
        try:
            print(f"Fetching hints from {url}...")
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find main content
            content = soup.find(['div', 'article'], class_=lambda x: x and 'entry-content' in str(x))
            if not content:
                content = soup.find('article')
            
            if not content:
                return {}
            
            hints_map = {}
            current_direction = None
            current_clue_id = None
            hint_buffer = []
            
            # Parse through elements
            for elem in content.find_all(['p', 'h2', 'h3', 'h4', 'strong']):
                text = elem.get_text().strip()
                
                if not text:
                    continue
                
                # Check for direction headers
                if re.match(r'^(across|down)$', text, re.IGNORECASE):
                    current_direction = text.lower()
                    continue
                
                # Check for clue line
                # Pattern: "1 ANSWER (7) Clue text"
                # or: "1a ANSWER (7) Clue text"
                clue_match = re.match(r'^(\d+[a-z]?)\s+([A-Z][A-Z\s\-\']+?)\s*\(([0-9,\-]+)\)', text)
                
                if clue_match and current_direction:
                    # Save previous clue
                    if current_clue_id and hint_buffer:
                        hints_map[current_clue_id] = hint_buffer
                        hint_buffer = []
                    
                    # Start new clue
                    clue_num = clue_match.group(1)
                    current_clue_id = f"{clue_num}-{current_direction}"
                
                elif current_clue_id and text:
                    # This is explanation text - add to buffer
                    # Skip very short lines and meta text
                    if (len(text) > 20 and 
                        not text.startswith('Posted') and
                        not text.startswith('This entry was') and
                        'comment' not in text.lower()):
                        hint_buffer.append(text)
            
            # Save last clue
            if current_clue_id and hint_buffer:
                hints_map[current_clue_id] = hint_buffer
            
            print(f"✓ Extracted hints for {len(hints_map)} clues")
            return hints_map
            
        except Exception as e:
            print(f"Error fetching hints: {e}")
            return {}


class HintGenerator:
    """Generate 4-level progressive hints from analysis text"""
    
    @staticmethod
    def generate_hints(hint_paragraphs: List[str]) -> List[str]:
        """
        Convert hint paragraphs into 4-level progressive hints
        
        Strategy:
        - Level 1: Definition hint
        - Level 2: Wordplay type
        - Level 3: Partial breakdown
        - Level 4: Full explanation
        """
        if not hint_paragraphs:
            return ['', '', '', '']
        
        full_text = ' '.join(hint_paragraphs)
        hints = ['', '', '', '']
        
        # Level 1: Definition
        # Look for "definition" or extract first concept
        def_pattern = r'(definition[^.]*\.)'
        def_match = re.search(def_pattern, full_text, re.IGNORECASE)
        
        if def_match:
            hints[0] = def_match.group(1).strip()
        else:
            # Take first sentence
            sentences = re.split(r'[.!?]+', full_text)
            if sentences:
                hints[0] = sentences[0].strip()[:150] + '.'
        
        # Level 2: Wordplay type
        wordplay_keywords = {
            'anagram': 'This is an anagram.',
            'reversal': 'This involves a reversal.',
            'hidden': 'The answer is hidden in the clue.',
            'charade': 'This is a charade (parts joined together).',
            'container': 'This is a container clue (one part inside another).',
            'homophone': 'This is a homophone (sounds like).',
            'double definition': 'This is a double definition.',
            'cryptic definition': 'This is a cryptic definition.',
        }
        
        for keyword, description in wordplay_keywords.items():
            if keyword in full_text.lower():
                hints[1] = description
                break
        
        if not hints[1]:
            hints[1] = "Look at how the clue breaks down into parts."
        
        # Level 3: Partial explanation
        # Try to give more detail without full answer
        if len(hint_paragraphs) > 1:
            hints[2] = hint_paragraphs[1][:200]
        else:
            # Extract key phrases
            middle = full_text[:300]
            hints[2] = middle
        
        # Level 4: Full explanation
        hints[3] = full_text
        
        return hints


class PuzzleScraper:
    """Main scraper that combines Guardian and fifteensquared data"""
    
    def __init__(self):
        self.guardian = GuardianScraper()
        self.fifteensquared = FifteensquaredScraper()
        self.hint_generator = HintGenerator()
    
    def scrape_puzzle(self, puzzle_number: str) -> Dict:
        """
        Complete scraping pipeline
        
        Returns dict with:
        {
            'publication': 'Guardian',
            'puzzle_number': '29916',
            'setter': 'Name',
            'date': '2026-01-29',
            'clues': [
                {
                    'clue_number': '1',
                    'direction': 'across',
                    'clue_text': '...',
                    'answer': 'ANSWER',
                    'enumeration': '7',
                    'hints': ['hint1', 'hint2', 'hint3', 'hint4']
                }
            ]
        }
        """
        print(f"\n{'='*60}")
        print(f"Scraping Guardian Cryptic #{puzzle_number}")
        print(f"{'='*60}\n")
        
        # Step 1: Get puzzle from Guardian
        puzzle_data = self.guardian.fetch_puzzle(puzzle_number)
        
        if 'error' in puzzle_data:
            return puzzle_data
        
        # Step 2: Try to get hints from fifteensquared
        post_url = self.fifteensquared.find_puzzle_post(puzzle_number)
        
        hints_map = {}
        if post_url:
            hints_map = self.fifteensquared.fetch_hints(post_url)
        
        # Step 3: Match hints to clues
        print("\nGenerating progressive hints...")
        for clue in puzzle_data['clues']:
            clue_id = f"{clue['clue_number']}-{clue['direction']}"
            
            if clue_id in hints_map:
                # Generate 4-level hints from the analysis
                hint_paragraphs = hints_map[clue_id]
                clue['hints'] = self.hint_generator.generate_hints(hint_paragraphs)
            else:
                # No hints found - use empty hints
                clue['hints'] = ['', '', '', '']
        
        print(f"✓ Puzzle scraping complete!")
        print(f"  - {len(puzzle_data['clues'])} clues")
        print(f"  - {len([c for c in puzzle_data['clues'] if any(c['hints'])])} with hints")
        
        return puzzle_data


# Test the scraper
if __name__ == '__main__':
    # This will only work where network is available (e.g., Railway)
    scraper = PuzzleScraper()
    
    # Test with a known puzzle
    result = scraper.scrape_puzzle('29915')
    
    if 'error' in result:
        print(f"\nError: {result['error']}")
    else:
        print(f"\n{'='*60}")
        print("Sample Output:")
        print(f"{'='*60}")
        print(f"Puzzle: {result['publication']} #{result['puzzle_number']}")
        print(f"Setter: {result['setter']}")
        print(f"Date: {result['date']}")
        print(f"Clues: {len(result['clues'])}")
        
        if result['clues']:
            clue = result['clues'][0]
            print(f"\nFirst clue:")
            print(f"  {clue['clue_number']} {clue['direction']}: {clue['clue_text']}")
            print(f"  Answer: {clue['answer']} ({clue['enumeration']})")
            print(f"  Hints available: {len([h for h in clue['hints'] if h])}/4")
