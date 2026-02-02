"""
Guardian Cryptic Puzzle Scraper - Enhanced Version

Fetches puzzles from Guardian and extracts hints from fifteensquared.net
With improved timeout handling and retry logic
"""

import requests
from bs4 import BeautifulSoup
import json
import re
import time
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
        """Fetch puzzle from Guardian with retry logic"""
        url = f"https://www.theguardian.com/crosswords/cryptic/{puzzle_number}"
        
        for attempt in range(3):
            try:
                print(f"Fetching Guardian puzzle {puzzle_number}... (attempt {attempt + 1}/3)")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                island = soup.find('gu-island', attrs={'name': 'CrosswordComponent'})
                
                if not island:
                    return {'error': 'Could not find crossword data on page'}
                
                props_json = island.get('props')
                if not props_json:
                    return {'error': 'No props attribute found'}
                
                props = json.loads(props_json)
                puzzle_data = props.get('data', {})
                
                result = {
                    'publication': 'Guardian',
                    'puzzle_number': str(puzzle_data.get('number', puzzle_number)),
                    'setter': puzzle_data.get('creator', {}).get('name', 'Unknown'),
                    'date': self._parse_date(puzzle_data.get('date')),
                    'clues': []
                }
                
                for entry in puzzle_data.get('entries', []):
                    clue = {
                        'clue_number': str(entry.get('number', '')),
                        'direction': entry.get('direction', 'across'),
                        'clue_text': entry.get('clue', ''),
                        'answer': entry.get('solution', ''),
                        'enumeration': str(entry.get('length', ''))
                    }
                    result['clues'].append(clue)
                
                print(f"✓ Successfully fetched {len(result['clues'])} clues from Guardian")
                return result
                
            except requests.exceptions.Timeout:
                print(f"⏱️ Guardian timeout on attempt {attempt + 1}")
                if attempt < 2:
                    time.sleep(2)
            except Exception as e:
                print(f"Error fetching Guardian: {e}")
                if attempt < 2:
                    time.sleep(2)
                else:
                    return {'error': str(e)}
        
        return {'error': 'Failed to fetch from Guardian after 3 attempts'}
    
    def _parse_date(self, timestamp) -> str:
        if timestamp:
            try:
                dt = datetime.fromtimestamp(timestamp / 1000)
                return dt.strftime('%Y-%m-%d')
            except:
                pass
        return datetime.now().strftime('%Y-%m-%d')


class FifteensquaredScraper:
    """Scrapes hint analysis from fifteensquared.net with robust error handling"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def find_puzzle_post(self, puzzle_number: str) -> Optional[str]:
        """Search for puzzle post with retries"""
        search_url = f"https://fifteensquared.net/?s=guardian+{puzzle_number}"
        
        for attempt in range(3):
            try:
                print(f"Searching fifteensquared... (attempt {attempt + 1}/3)")
                response = self.session.get(search_url, timeout=30)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Method 1: Look in articles
                articles = soup.find_all('article')
                for article in articles:
                    title_elem = article.find(['h2', 'h1'])
                    if title_elem:
                        link = title_elem.find('a', href=True)
                        if link and puzzle_number in link['href']:
                            print(f"✓ Found post: {link['href']}")
                            return link['href']
                
                # Method 2: Look in all links
                links = soup.find_all('a', href=True)
                for link in links:
                    href = link.get('href', '')
                    if f'guardian-{puzzle_number}' in href.lower() and 'fifteensquared.net' in href:
                        print(f"✓ Found post: {href}")
                        return href
                
                print("✗ No fifteensquared post found")
                return None
                
            except requests.exceptions.Timeout:
                print(f"⏱️ Fifteensquared timeout on attempt {attempt + 1}/3")
                if attempt < 2:
                    print("   Waiting 3 seconds before retry...")
                    time.sleep(3)
            except Exception as e:
                print(f"Error: {e}")
                if attempt < 2:
                    time.sleep(3)
        
        print("✗ Could not reach fifteensquared after 3 attempts")
        return None
    
    def fetch_hints(self, url: str) -> Dict[str, List[str]]:
        """Fetch hints from post with retry logic"""
        for attempt in range(3):
            try:
                print(f"Fetching hints from post... (attempt {attempt + 1}/3)")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                content = soup.find(['div', 'article'], class_=lambda x: x and 'entry-content' in str(x))
                if not content:
                    content = soup.find('article')
                
                if not content:
                    return {}
                
                hints_map = {}
                current_direction = None
                current_clue_id = None
                hint_buffer = []
                
                for elem in content.find_all(['p', 'h2', 'h3', 'h4', 'strong']):
                    text = elem.get_text().strip()
                    if not text:
                        continue
                    
                    # Check for direction
                    if re.match(r'^(across|down)$', text, re.IGNORECASE):
                        current_direction = text.lower()
                        continue
                    
                    # Check for clue line
                    clue_match = re.match(r'^(\d+[a-z]?)\s+([A-Z][A-Z\s\-\']+?)\s*\(([0-9,\-]+)\)', text)
                    
                    if clue_match and current_direction:
                        if current_clue_id and hint_buffer:
                            hints_map[current_clue_id] = hint_buffer
                            hint_buffer = []
                        
                        clue_num = clue_match.group(1)
                        current_clue_id = f"{clue_num}-{current_direction}"
                    
                    elif current_clue_id and text and len(text) > 20:
                        if not any(skip in text.lower() for skip in ['posted', 'comment', 'this entry was']):
                            hint_buffer.append(text)
                
                if current_clue_id and hint_buffer:
                    hints_map[current_clue_id] = hint_buffer
                
                print(f"✓ Extracted hints for {len(hints_map)} clues")
                return hints_map
                
            except requests.exceptions.Timeout:
                print(f"⏱️ Timeout fetching hints (attempt {attempt + 1}/3)")
                if attempt < 2:
                    time.sleep(3)
            except Exception as e:
                print(f"Error fetching hints: {e}")
                if attempt < 2:
                    time.sleep(3)
        
        return {}


class HintGenerator:
    """Generate progressive hints from analysis"""
    
    @staticmethod
    def generate_hints(hint_paragraphs: List[str]) -> List[str]:
        if not hint_paragraphs:
            return ['', '', '', '']
        
        full_text = ' '.join(hint_paragraphs)
        hints = ['', '', '', '']
        
        # Level 1: Definition
        def_match = re.search(r'(definition[^.]*\.)', full_text, re.IGNORECASE)
        if def_match:
            hints[0] = def_match.group(1).strip()
        else:
            sentences = re.split(r'[.!?]+', full_text)
            if sentences:
                hints[0] = sentences[0].strip()[:150] + '.'
        
        # Level 2: Wordplay type
        wordplay_keywords = {
            'anagram': 'This is an anagram.',
            'reversal': 'This involves a reversal.',
            'hidden': 'The answer is hidden in the clue.',
            'charade': 'This is a charade (parts joined together).',
            'container': 'This is a container clue.',
            'homophone': 'This is a homophone (sounds like).',
        }
        
        for keyword, description in wordplay_keywords.items():
            if keyword in full_text.lower():
                hints[1] = description
                break
        
        if not hints[1]:
            hints[1] = "Look at how the clue breaks down."
        
        # Level 3: Partial
        if len(hint_paragraphs) > 1:
            hints[2] = hint_paragraphs[1][:250]
        else:
            hints[2] = full_text[:250]
        
        # Level 4: Full
        hints[3] = full_text
        
        return hints


class PuzzleScraper:
    """Main scraper combining all sources"""
    
    def __init__(self):
        self.guardian = GuardianScraper()
        self.fifteensquared = FifteensquaredScraper()
        self.hint_generator = HintGenerator()
    
    def scrape_puzzle(self, puzzle_number: str) -> Dict:
        print(f"\n{'='*60}")
        print(f"Scraping Guardian Cryptic #{puzzle_number}")
        print(f"{'='*60}\n")
        
        # Step 1: Guardian
        puzzle_data = self.guardian.fetch_puzzle(puzzle_number)
        if 'error' in puzzle_data:
            return puzzle_data
        
        # Step 2: Fifteensquared
        print("\nSearching for hints on fifteensquared.net...")
        post_url = self.fifteensquared.find_puzzle_post(puzzle_number)
        
        hints_map = {}
        if post_url:
            hints_map = self.fifteensquared.fetch_hints(post_url)
        else:
            print("⚠️  No hints available - will import with blank hints")
        
        # Step 3: Match hints
        print("\nProcessing hints...")
        for clue in puzzle_data['clues']:
            clue_id = f"{clue['clue_number']}-{clue['direction']}"
            
            if clue_id in hints_map:
                hint_paragraphs = hints_map[clue_id]
                clue['hints'] = self.hint_generator.generate_hints(hint_paragraphs)
            else:
                clue['hints'] = ['', '', '', '']
        
        clues_with_hints = len([c for c in puzzle_data['clues'] if any(c['hints'])])
        print(f"\n✓ Complete! {clues_with_hints}/{len(puzzle_data['clues'])} clues have hints")
        
        return puzzle_data
