#!/usr/bin/env python
"""
Launcher script for SurgiBot Display.
Run this to show the large screen display.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from surgibot.server.display import run_display

if __name__ == "__main__":
    print("=" * 60)
    print("🖥️  SurgiBot Display - Large Screen Monitor")
    print("=" * 60)
    print()
    print("Starting display window...")
    print("Make sure API server is running at http://localhost:8088")
    print()
    print("Press ESC to exit fullscreen")
    print("Close window to quit")
    print()

    try:
        run_display()
    except KeyboardInterrupt:
        print("\nDisplay stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
