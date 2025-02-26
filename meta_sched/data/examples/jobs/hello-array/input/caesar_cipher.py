#! /usr/bin/env python3

import sys
from math import ceil
from multiprocessing import Pool
from pathlib import Path

if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} <filename> <shift-count>", file=sys.stderr)
    exit(1)

input_file = Path(sys.argv[1])
offset = int(sys.argv[2])
output_file = Path() / input_file.with_suffix(f".c{offset}{input_file.suffix}").name


def char_range(first: str, last: str) -> str:
    assert ord(first) <= ord(last)
    return "".join([chr(i) for i in range(ord(first), ord(last) + 1)])


alphabet = char_range("A", "Z") + char_range("a", "z") + char_range("0", "9")


def shift(char: str, offset: int) -> str:
    assert len(char) == 1
    i = alphabet.find(char)
    if i < 0:
        return char  # leave unknown unencrypted
    while offset < 0:
        offset += len(alphabet)
    return alphabet[(i + offset) % len(alphabet)]


def encrypt(text: str) -> str:
    global offset
    return "".join([shift(c, offset) for c in text])


print(f"Encrypting {input_file} with shift {offset}...")
text = input_file.read_text()
lines = text.splitlines(keepends=True)
pool = Pool()
pool_size = eval("len(pool._pool)")
print(f"(Processing {len(lines)} lines in {pool_size} parallel batches.)")
lines = pool.map(encrypt, lines, ceil(len(lines) / pool_size))
pool.close()
text = "".join(lines)
print(f"Writing encrypted text to {output_file}...")
output_file.write_text(text)
print("Done!")
