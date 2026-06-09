import sys
from pathlib import Path

# Make project root importable so we can import the FastAPI app
# located in the `investsim` package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from investsim.web_app import app

# Expose FastAPI `app` for Vercel's Python serverless builder.
