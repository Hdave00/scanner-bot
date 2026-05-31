import importlib

import pytest


@pytest.fixture
def attbot_module(monkeypatch):
    monkeypatch.setenv("TOKEN", "test-token")
    monkeypatch.setenv("CHANNEL_ID", "12345678901234567")
    monkeypatch.setenv("GUILD_ID", "12345678901234567")

    import discord.ext.commands as commands
    monkeypatch.setattr(commands.Bot, "run", lambda self, *args, **kwargs: None)

    from bots import attbot
    return importlib.reload(attbot)

def test_lowercase(attbot_module):
    assert attbot_module.normalize_name("Miller") == "miller"
    assert attbot_module.normalize_name("MILLER") == "miller"
    assert attbot_module.normalize_name("milleR") == "miller"

def test_remove_punctuation(attbot_module):
    # '.' ',' '-' '!' are still stripped as before
    assert attbot_module.normalize_name("Cpl. A. Miller!") == "cpl a miller"
    assert attbot_module.normalize_name("Cpl- A, Miller!") == "cpl a miller"
    assert attbot_module.normalize_name("Cpl. A Miller.") == "cpl a miller"

def test_whitespace_collapse(attbot_module):
    assert attbot_module.normalize_name("  A   Miller   ") == "a miller"

def test_mixed_case(attbot_module):
    assert attbot_module.normalize_name("CpL M. MoOsEs") == "cpl m mooses"

def test_special_characters(attbot_module):
    assert attbot_module.normalize_name("User#1234") == "user1234"
    assert attbot_module.normalize_name("User&1234") == "user1234"
    # '/' is intentionally NOT stripped — see test_slash_preserved_for_ranks
    assert attbot_module.normalize_name("User/1234") == "user/1234"

# New test: '/' is preserved for rank formats like MSPC/5
def test_slash_preserved_for_ranks(attbot_module):
    assert attbot_module.normalize_name("MSPC/5") == "mspc/5"
    assert attbot_module.normalize_name("LCPL/3") == "lcpl/3"
    # Ensures promoted members stay distinct after normalization
    assert attbot_module.normalize_name("MSPC/5") != attbot_module.normalize_name("MSPC/6")

