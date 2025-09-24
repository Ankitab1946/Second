import sys, os
import pytest

# Ensure "src" is on sys.path so `import app...` works
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_dir = os.path.join(root_dir, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

def pytest_configure(config):
    config.addinivalue_line("markers", "bdd: BDD scenarios")
    config.addinivalue_line("markers", "smoke: Smoke tests")
    config.addinivalue_line("markers", "regression: Regression tests")
