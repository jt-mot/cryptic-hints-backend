#!/usr/bin/env python3
"""
Puzzle Import and Archive Management System

This script handles:
- Importing new puzzles
- Archiving old puzzles
- Managing puzzle database
- Generating hints automatically
"""

import json
import os
from datetime import datetime
from pathlib import Path

class PuzzleManager:
    def __init__(self, data_dir='puzzle_data'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        self.active_file = self.data_dir / 'active_puzzle.json'
        self.archive_dir = self.data_dir / 'archive'
        self.archive_dir.mkdir(exist_ok=True)
    
    def import_puzzle(self, puzzle_number, date, setter, clues_data):
        """
        Import a new puzzle and archive the current one if exists
        
        Args:
            puzzle_number: Guardian puzzle number (e.g., "29915")
            date: Publication date (YYYY-MM-DD)
            setter: Setter name
            clues_data: Dict with 'across' and 'down' clues
        """
        # Archive current puzzle if it exists
        if self.active_file.exists():
            self.archive_current()
        
        # Create new puzzle data
        puzzle = {
            'number': puzzle_number,
            'date': date,
            'setter': setter,
            'clues': clues_data,
            'hints': self.generate_hints(clues_data),
            'imported_at': datetime.now().isoformat(),
            'status': 'active'
        }
        
        # Save as active puzzle
        with open(self.active_file, 'w') as f:
            json.dump(puzzle, f, indent=2)
        
        print(f"✅ Puzzle #{puzzle_number} imported successfully!")
        return puzzle
    
    def archive_current(self):
        """Archive the currently active puzzle"""
        if not self.active_file.exists():
            print("No active puzzle to archive")
            return
        
        with open(self.active_file, 'r') as f:
            puzzle = json.load(f)
        
        # Update status
        puzzle['status'] = 'archived'
        puzzle['archived_at'] = datetime.now().isoformat()
        
        # Save to archive
        archive_file = self.archive_dir / f"puzzle_{puzzle['number']}.json"
        with open(archive_file, 'w') as f:
            json.dump(puzzle, f, indent=2)
        
        print(f"📦 Puzzle #{puzzle['number']} archived")
    
    def get_active_puzzle(self):
        """Get the currently active puzzle"""
        if not self.active_file.exists():
            return None
        
        with open(self.active_file, 'r') as f:
            return json.load(f)
    
    def get_archived_puzzles(self):
        """Get list of all archived puzzles"""
        puzzles = []
        for file in self.archive_dir.glob('puzzle_*.json'):
            with open(file, 'r') as f:
                puzzles.append(json.load(f))
        
        # Sort by number (descending)
        puzzles.sort(key=lambda p: int(p['number']), reverse=True)
        return puzzles
    
    def make_puzzle_active(self, puzzle_number):
        """Make an archived puzzle the active one"""
        archive_file = self.archive_dir / f"puzzle_{puzzle_number}.json"
        
        if not archive_file.exists():
            raise ValueError(f"Puzzle #{puzzle_number} not found in archive")
        
        # Archive current if exists
        if self.active_file.exists():
            self.archive_current()
        
        # Load archived puzzle
        with open(archive_file, 'r') as f:
            puzzle = json.load(f)
        
        # Update status
        puzzle['status'] = 'active'
        puzzle['reactivated_at'] = datetime.now().isoformat()
        
        # Save as active
        with open(self.active_file, 'w') as f:
            json.dump(puzzle, f, indent=2)
        
        print(f"✅ Puzzle #{puzzle_number} is now active")
        return puzzle
    
    def generate_hints(self, clues_data):
        """
        Generate progressive hints for all clues
        
        This is a placeholder - in production, this would use AI hint generation
        """
        hints = {'across': {}, 'down': {}}
        
        for direction in ['across', 'down']:
            for number, clue_info in clues_data.get(direction, {}).items():
                hints[direction][number] = {
                    'hint1': f"Start by identifying the definition in this clue",
                    'hint2': f"Look for wordplay indicators",
                    'hint3': f"The answer is {clue_info['length']} letters long",
                    'answer': ""  # Would be filled in during review
                }
        
        return hints
    
    def parse_text_clues(self, text):
        """
        Parse clues from text format
        
        Example input:
        Across
        1 Prisoner finally does bird over murder (7)
        5 Spooner's old man wagered unrecoverable liability (3,4)
        
        Down
        2 Visual is current with work coming up (7)
        """
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        result = {'across': {}, 'down': {}}
        current_section = None
        
        for line in lines:
            lower_line = line.lower()
            
            if lower_line == 'across' or lower_line.startswith('across'):
                current_section = 'across'
                continue
            elif lower_line == 'down' or lower_line.startswith('down'):
                current_section = 'down'
                continue
            
            # Parse clue: "NUMBER clue text (LENGTH)"
            import re
            match = re.match(r'^(\d+)\s+(.+?)\s+\(([0-9,-]+)\)\s*$', line)
            if match and current_section:
                number, clue, length = match.groups()
                result[current_section][number] = {
                    'clue': clue.strip(),
                    'length': length
                }
        
        return result


# Example usage
if __name__ == '__main__':
    manager = PuzzleManager()
    
    # Example: Import puzzle 29915
    print("=" * 60)
    print("PUZZLE IMPORT DEMO")
    print("=" * 60)
    
    # This is sample data - in practice, you'd paste real clues
    sample_clues = {
        'across': {
            '1': {'clue': 'Sample clue text here', 'length': '7'},
            '5': {'clue': 'Another clue', 'length': '3,4'},
        },
        'down': {
            '2': {'clue': 'Down clue example', 'length': '7'},
        }
    }
    
    # Show current state
    current = manager.get_active_puzzle()
    if current:
        print(f"\n📍 Current active puzzle: #{current['number']}")
    else:
        print("\n📍 No active puzzle")
    
    archived = manager.get_archived_puzzles()
    print(f"📚 Archived puzzles: {len(archived)}")
    for p in archived:
        print(f"   - #{p['number']} ({p['date']})")
    
    print("\n" + "=" * 60)
    print("To import puzzle 29915, use:")
    print("manager.import_puzzle('29915', '2026-01-28', 'Setter Name', clues_data)")
    print("=" * 60)
