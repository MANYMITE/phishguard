#!/usr/bin/env python3
"""PhishGuard terminal UI launcher:  python phishguard-cli.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from phishguard.cli import main

if __name__ == "__main__":
    main()
