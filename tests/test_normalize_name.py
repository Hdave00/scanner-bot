import pytest
from bots.attbot import normalize_name

def test_lowercase():
    assert normalize_name("Miller") == "miller"
    assert normalize_name("MILLER") == "miller"
    assert normalize_name("milleR") == "miller"

def test_remove_punctuation():
    assert normalize_name("Cpl. A. Miller!") == "cpl a miller"
    assert normalize_name("Cpl- A, Miller!") == "cpl a miller"
    assert normalize_name("Cpl. A Miller.") == "cpl a miller"

def test_whitespace_collapse():
    assert normalize_name("  A   Miller   ") == "a miller"

def test_mixed_case():
    assert normalize_name("CpL M. MoOsEs") == "cpl m mooses"

def test_special_characters():
    assert normalize_name("User#1234") == "user1234"
    assert normalize_name("User&1234") == "user1234"

