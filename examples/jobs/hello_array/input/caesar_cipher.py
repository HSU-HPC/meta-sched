#! /usr/bin/env python3

import sys
from pathlib import Path

if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} <filename> <shift-count>", file=sys.stderr)
    exit(1)

input_file = Path(sys.argv[1])
shift = int(sys.argv[2])
output_file = Path() / input_file.with_suffix(f".c{shift}{input_file.suffix}").name

print(f"Encrypting {input_file} with shift {shift} to {output_file}...", end="")
text = input_file.read_text()
text = "".join([chr(ord(c) + shift) for c in text])
output_file.write_text(text)
print("Done!")
