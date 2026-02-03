"""
Crossword Grid Builder - Working Prototype

Builds grids from Guardian crossword JSON data
"""

import json
from typing import Dict, List, Optional, Tuple


class CrosswordGrid:
    """
    Represents a crossword grid with letters, numbers, and metadata
    """
    
    def __init__(self, size: int = 15):
        self.size = size
        self.grid = [[None for _ in range(size)] for _ in range(size)]
        self.numbers = [[None for _ in range(size)] for _ in range(size)]
        self.clue_cells = {}  # clue_id -> list of (x, y) tuples
        self.cell_clues = {}  # (x, y) -> list of clue_ids
    
    def set_cell(self, x: int, y: int, letter: str, clue_id: str, number: Optional[int] = None):
        """Set a cell in the grid"""
        if x < 0 or x >= self.size or y < 0 or y >= self.size:
            raise ValueError(f"Position ({x}, {y}) out of bounds")
        
        # Set letter
        existing_letter = self.grid[y][x]
        if existing_letter is not None and existing_letter != letter:
            print(f"WARNING: Letter conflict at ({x}, {y}): '{existing_letter}' vs '{letter}'")
        self.grid[y][x] = letter
        
        # Set number (if starting cell)
        if number is not None and self.numbers[y][x] is None:
            self.numbers[y][x] = number
        
        # Track clue associations
        if clue_id not in self.clue_cells:
            self.clue_cells[clue_id] = []
        self.clue_cells[clue_id].append((x, y))
        
        if (x, y) not in self.cell_clues:
            self.cell_clues[(x, y)] = []
        if clue_id not in self.cell_clues[(x, y)]:
            self.cell_clues[(x, y)].append(clue_id)
    
    def to_dict(self) -> Dict:
        """Export as dictionary"""
        return {
            'size': self.size,
            'grid': self.grid,
            'numbers': self.numbers,
            'clue_cells': {clue_id: cells for clue_id, cells in self.clue_cells.items()},
            'cell_clues': {f"{x},{y}": clues for (x, y), clues in self.cell_clues.items()}
        }
    
    def to_display_string(self, show_answers: bool = True) -> str:
        """Create ASCII representation of grid"""
        lines = []
        lines.append("+" + "---+" * self.size)
        
        for y in range(self.size):
            row = "|"
            for x in range(self.size):
                letter = self.grid[y][x]
                number = self.numbers[y][x]
                
                if letter is None:
                    # Black square
                    row += "███|"
                else:
                    # White square
                    if number:
                        if show_answers:
                            row += f"{number:2}{letter}|"
                        else:
                            row += f"{number:2} |"
                    else:
                        if show_answers:
                            row += f"  {letter}|"
                        else:
                            row += "   |"
            
            lines.append(row)
            lines.append("+" + "---+" * self.size)
        
        return "\n".join(lines)


class GridBuilder:
    """
    Builds crossword grids from Guardian JSON data
    """
    
    def __init__(self, puzzle_data: Dict):
        self.puzzle_data = puzzle_data
        self.entries = puzzle_data.get('entries', [])
        self.dimensions = puzzle_data.get('dimensions', {'rows': 15, 'cols': 15})
    
    def build(self) -> CrosswordGrid:
        """
        Build the complete grid
        
        Returns:
            CrosswordGrid object
        """
        # Determine grid size
        grid_size = self._detect_grid_size()
        grid = CrosswordGrid(grid_size)
        
        # Place each entry
        for entry in self.entries:
            self._place_entry(grid, entry)
        
        return grid
    
    def _detect_grid_size(self) -> int:
        """
        Detect grid size from entries
        
        Returns:
            Grid size (typically 15 or 23)
        """
        # Check if dimensions are provided
        if 'rows' in self.dimensions:
            return max(self.dimensions['rows'], self.dimensions.get('cols', self.dimensions['rows']))
        
        # Calculate from entry positions and lengths
        max_pos = 0
        for entry in self.entries:
            pos = entry['position']
            x, y = pos['x'], pos['y']
            length = entry['length']
            direction = entry['direction']
            
            if direction == 'across':
                max_pos = max(max_pos, x + length)
            else:
                max_pos = max(max_pos, y + length)
        
        # Round up to nearest standard size
        if max_pos <= 15:
            return 15
        elif max_pos <= 23:
            return 23
        else:
            return max_pos
    
    def _place_entry(self, grid: CrosswordGrid, entry: Dict):
        """
        Place an entry in the grid
        
        Args:
            grid: CrosswordGrid to place entry in
            entry: Entry dict from Guardian JSON
        """
        clue_id = entry['id']
        number = entry['number']
        position = entry['position']
        x, y = position['x'], position['y']
        answer = entry['solution']
        direction = entry['direction']
        
        # Place each letter
        for i, letter in enumerate(answer):
            if direction == 'across':
                cell_x, cell_y = x + i, y
            else:  # down
                cell_x, cell_y = x, y + i
            
            # First letter gets the clue number
            cell_number = number if i == 0 else None
            
            grid.set_cell(cell_x, cell_y, letter, clue_id, cell_number)
    
    def build_and_export(self) -> Dict:
        """
        Build grid and export as dict
        
        Returns:
            Dict with grid data ready for JSON serialization
        """
        grid = self.build()
        return grid.to_dict()


def build_grid_from_json_file(filepath: str) -> CrosswordGrid:
    """
    Build grid from Guardian JSON file
    
    Args:
        filepath: Path to JSON file
    
    Returns:
        CrosswordGrid object
    """
    with open(filepath, 'r') as f:
        puzzle_data = json.load(f)
    
    builder = GridBuilder(puzzle_data)
    return builder.build()


def demo():
    """
    Demo with sample data
    """
    # Sample Guardian puzzle data
    sample_data = {
        "id": "simple/1",
        "number": 1,
        "name": "Simple Crossword #1",
        "dimensions": {"rows": 7, "cols": 7},
        "entries": [
            {
                "id": "1-across",
                "number": 1,
                "clue": "Toy on a string (2-2)",
                "direction": "across",
                "length": 4,
                "position": {"x": 0, "y": 0},
                "solution": "YOYO"
            },
            {
                "id": "4-across",
                "number": 4,
                "clue": "Have a rest (3,4)",
                "direction": "across",
                "length": 7,
                "position": {"x": 0, "y": 3},
                "solution": "LIEDOWN"
            },
            {
                "id": "1-down",
                "number": 1,
                "clue": "Colour (6)",
                "direction": "down",
                "length": 6,
                "position": {"x": 0, "y": 0},
                "solution": "YELLOW"
            },
            {
                "id": "2-down",
                "number": 2,
                "clue": "Bits and bobs (4,3,4)",
                "direction": "down",
                "length": 7,
                "position": {"x": 3, "y": 0},
                "solution": "ODDSAND"
            }
        ]
    }
    
    print("Building grid from sample data...")
    builder = GridBuilder(sample_data)
    grid = builder.build()
    
    print("\nGrid (with answers):")
    print(grid.to_display_string(show_answers=True))
    
    print("\nGrid (blank):")
    print(grid.to_display_string(show_answers=False))
    
    print("\nGrid data as JSON:")
    print(json.dumps(grid.to_dict(), indent=2))


if __name__ == '__main__':
    demo()
