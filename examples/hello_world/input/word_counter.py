#! /usr/bin/env python3

from pathlib import Path

text = (Path(__file__).parent / "lorem_ipsum.txt").read_text()
words = [word for word in text.replace("\n", " ").split(" ") if len(word.strip()) > 0]

print(f"{len(words)} words")
