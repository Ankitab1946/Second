import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load_config():
    p = ROOT / "config" / "config.yaml"
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)
