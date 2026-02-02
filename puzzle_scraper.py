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

from enhanced_hints import EnhancedHintGenerator, AuthorStyleDetector



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
                print(f"   URL: {search_url}")
                response = self.session.get(search_url, timeout=30)
                print(f"   Got response: {response.status_code}")
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Method 1: Look in articles
                articles = soup.find_all('article')
                print(f"   Found {len(articles)} articles in search results")
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
        """Fetch hints from post with retry logic and flexible parsing"""
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
                    print("⚠️  Could not find main content area")
                    return {}
                
                hints_map = {}
                current_direction = None
                
                # FIRST: Extract ALL definitions from entire content
                # PeterO uses: <span style="...italic...underline">definition</span>
                all_definitions_by_text = {}
                
                # DEBUG: Check what we're actually getting
                all_paras = content.find_all('p')
                print(f"   DEBUG: Content has {len(all_paras)} paragraphs")
                
                all_spans = content.find_all('span')
                print(f"   DEBUG: Content has {len(all_spans)} total spans")
                
                styled_spans = content.find_all('span', style=True)
                print(f"   DEBUG: Found {len(styled_spans)} spans with style attribute")
                
                if styled_spans:
                    # Show first few styles
                    for i, span in enumerate(styled_spans[:3]):
                        print(f"   DEBUG: Span {i+1} style: {span.get('style')[:100]}")
                        print(f"   DEBUG: Span {i+1} text: {span.get_text()[:50]}")
                
                # Search ALL styled spans in content (not just in paragraphs)
                for span in styled_spans:
                    style = span.get('style', '').lower()
                    # Check if style has both italic and underline
                    if 'italic' in style and 'underline' in style:
                        def_text = span.get_text().strip()
                        if len(def_text) > 2:
                            # Use span text as both key and value for now
                            all_definitions_by_text[def_text] = def_text
                
                print(f"   DEBUG: Found {len(all_definitions_by_text)} definitions with italic+underline style")
                if all_definitions_by_text:
                    print(f"   DEBUG: Sample definitions: {list(all_definitions_by_text.values())[:3]}")
                
                # Strategy: Get text content and split by lines, but also keep HTML for parsing
                full_text = content.get_text()
                lines = [line.strip() for line in full_text.split('\n') if line.strip()]
                
                # Also get all paragraphs to extract HTML-based definitions
                all_paragraphs = content.find_all('p')
                
                print(f"   Processing {len(lines)} lines of text...")
                
                i = 0
                while i < len(lines):
                    line = lines[i]
                    
                    # Check for direction marker
                    if re.match(r'^(ACROSS|DOWN)$', line, re.IGNORECASE):
                        current_direction = line.lower()
                        print(f"   Found direction: {current_direction}")
                        i += 1
                        continue
                    
                    # Check if this is a clue number
                    if current_direction and re.match(r'^\d+[a-z]?$', line):
                        clue_num = line
                        
                        # Next line should be the answer
                        if i + 1 < len(lines):
                            answer_line = lines[i + 1]
                            
                            # Check if it looks like an answer (uppercase words)
                            if re.match(r'^[A-Z][A-Z\s\-\']+$', answer_line):
                                clue_id = f"{clue_num}-{current_direction}"
                                print(f"   Found clue: {clue_id} - {answer_line}")
                                
                                # Collect explanation text
                                hint_buffer = []
                                j = i + 2  # Start after answer
                                
                                # Also find ALL definitions in this clue's paragraphs
                                html_definitions = []
                                
                                while j < len(lines):
                                    next_line = lines[j]
                                    
                                    # Stop if we hit another clue number or direction
                                    if re.match(r'^\d+[a-z]?$', next_line):
                                        break
                                    if re.match(r'^(ACROSS|DOWN)$', next_line, re.IGNORECASE):
                                        break
                                    
                                    # Skip meta text
                                    skip_phrases = ['posted', 'comment', 'tagged', 'bookmark', 
                                                   'permalink', 'navigation', 'leave a reply',
                                                   'you must be logged', 'fill in your details',
                                                   'the puzzle may be found']
                                    
                                    if not any(skip in next_line.lower() for skip in skip_phrases):
                                        if len(next_line) > 10:
                                            hint_buffer.append(next_line)
                                    
                                    j += 1
                                
                                # Use extracted definitions - just assign all of them for now
                                # (Could be smarter about matching specific ones to clues later)
                                html_definitions = list(all_definitions_by_text.values())
                                
                                if hint_buffer:
                                    # Store both text and extracted definitions
                                    hints_map[clue_id] = {
                                        'text': hint_buffer,
                                        'definitions': html_definitions[:1] if html_definitions else []  # Just use first definition for each clue
                                    }
                                    if html_definitions:
                                        print(f"      -> {len(hint_buffer)} hint lines, {len(html_definitions[:1])} definitions: {html_definitions[:1]}")
                                    else:
                                        print(f"      -> {len(hint_buffer)} hint lines, 0 definitions")
                                
                                i = j - 1  # Continue from where we stopped
                    
                    i += 1
                
                print(f"✓ Extracted hints for {len(hints_map)} clues")
                return hints_map
                
            except requests.exceptions.Timeout:
                print(f"⏱️ Timeout fetching hints (attempt {attempt + 1}/3)")
                if attempt < 2:
                    time.sleep(3)
            except Exception as e:
                print(f"Error fetching hints: {e}")
                import traceback
                traceback.print_exc()
                if attempt < 2:
                    time.sleep(3)
        
        return {}


class PuzzleScraper:
    """Main scraper combining all sources"""
    
    def __init__(self):
        self.guardian = GuardianScraper()
        self.fifteensquared = FifteensquaredScraper()
        self.hint_generator = EnhancedHintGenerator()
        self.style_detector = AuthorStyleDetector()
        self.current_url = ''
        self.detected_author = 'generic'
    
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
            self.current_url = post_url
            
            # Fetch the full page content for author detection
            try:
                response = self.fifteensquared.session.get(post_url, timeout=30)
                page_content = response.text
            except:
                page_content = ''
            
            hints_map = self.fifteensquared.fetch_hints(post_url)
            
            # Detect author style using full page content
            self.detected_author = self.style_detector.detect_author(post_url, page_content)
            print(f"   Detected author style: {self.detected_author}")
        else:
            print("⚠️  No hints available - will import with blank hints")
        
        # Step 3: Match hints
        print("\nProcessing hints...")
        for clue in puzzle_data['clues']:
            clue_id = f"{clue['clue_number']}-{clue['direction']}"
            
            if clue_id in hints_map:
                hint_data = hints_map[clue_id]
                
                # Handle both old format (list) and new format (dict)
                if isinstance(hint_data, dict):
                    hint_paragraphs = hint_data['text']
                    definitions = hint_data.get('definitions', [])
                else:
                    hint_paragraphs = hint_data
                    definitions = []
                
                # Generate hints using detected author style, passing definitions
                clue['hints'] = self.hint_generator.generate_hints(
                    hint_paragraphs, 
                    self.detected_author,
                    definitions=definitions
                )
                
                # Debug: Check first clue
                if clue['clue_number'] == '1' and clue['direction'] == 'across':
                    print(f"\n   DEBUG - First clue:")
                    print(f"   Definitions found: {definitions}")
                    print(f"   Generated hints:")
                    for i, h in enumerate(clue['hints'], 1):
                        print(f"   Hint {i}: {h[:100] if h else '[EMPTY]'}")
            else:
                clue['hints'] = ['', '', '', '']
        
        clues_with_hints = len([c for c in puzzle_data['clues'] if any(c['hints'])])
        print(f"\n✓ Complete! {clues_with_hints}/{len(puzzle_data['clues'])} clues have hints")
        
        return puzzle_data
