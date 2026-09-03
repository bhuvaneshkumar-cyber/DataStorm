import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('src/App.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find all lines with potential single-quote-inside-single-quote issues
# Look for patterns like: 'text'text or ('text'text
for i, line in enumerate(lines):
    stripped = line.rstrip()
    # Count single quotes
    sq_count = stripped.count("'")
    # If a line has more than 2 single quotes and contains common contractions
    contractions = ["'re ", "'ll ", "'ve ", "'t ", "'s ", "'d ", "'m "]
    for c in contractions:
        if c in stripped:
            # Check if this contraction is inside a string literal (between quotes)
            idx = stripped.find(c)
            # Count quotes before this position
            before = stripped[:idx].count("'")
            if before % 2 == 1:  # Inside a single-quoted string
                print(f"L{i+1}: {stripped}")
                break
