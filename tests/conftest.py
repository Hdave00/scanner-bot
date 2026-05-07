from pathlib import Path
import sys
import os


ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)


os.environ.setdefault("TOKEN", "test-token")
os.environ.setdefault("CHANNEL_ID", "12345678901234567")
os.environ.setdefault("GUILD_ID", "12345678901234567")