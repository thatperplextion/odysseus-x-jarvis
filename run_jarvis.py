#!/usr/bin/env python3
"""
Run Jarvis OS standalone (without full Odysseus web server)
For integrated mode, Jarvis starts automatically with Odysseus via app.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from JARVIS.jarvis_core import main

if __name__ == "__main__":
    asyncio.run(main())
