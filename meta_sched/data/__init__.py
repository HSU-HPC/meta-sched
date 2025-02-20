from pathlib import Path


def get_examples_dir() -> Path:
    return Path(__file__).parent / "examples"
