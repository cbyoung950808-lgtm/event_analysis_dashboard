"""Streamlit Cloud entrypoint; launch from the repository root."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parent / 'analysis' / 'dashboard.py'), run_name='__main__')
