import sys
from pathlib import Path

# Tests import the backend package as if from the backend root, which is how
# uvicorn runs it too.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
