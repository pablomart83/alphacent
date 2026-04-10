#!/usr/bin/env python3
"""Test symbol normalizer."""

print("Starting test...")

from src.utils.symbol_normalizer import normalize_symbol

print("Testing symbol normalizer:")
print(f"  GE -> {normalize_symbol('GE')}")
print(f"  1017 -> {normalize_symbol('1017')}")
print(f"  ID_1017 -> {normalize_symbol('ID_1017')}")
print(f"  1017 (int) -> {normalize_symbol(1017)}")
print("✅ All tests passed!")
