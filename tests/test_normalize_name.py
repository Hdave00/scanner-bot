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

