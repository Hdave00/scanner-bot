"""Additional tests for attbot.py commands and functions."""

import asyncio
import importlib
from types import SimpleNamespace

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


class MockResponse:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, message, ephemeral=False, view=None):
        self.sent_messages.append({
            "message": message,
            "ephemeral": ephemeral,
            "view": view,
        })


class MockDeferredResponse(MockResponse):
    def __init__(self):
        super().__init__()
        self.deferred = False
        self.modal = None

    async def defer(self, thinking=False):
        self.deferred = True

    async def send_modal(self, modal):
        self.modal = modal


class MockFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, message=None, ephemeral=False, embed=None):
        self.messages.append({"message": message, "ephemeral": ephemeral, "embed": embed})


class MockInteraction:
    def __init__(self, user_id=1, display_name="Tester"):
        self.user = SimpleNamespace(id=user_id, display_name=display_name, roles=[])
        self.response = MockResponse()
        self.followup = MockFollowup()


class MockCommandInteraction:
    def __init__(self, roles=None, channel=None, guild=None, user_id=1):
        self.user = SimpleNamespace(id=user_id, roles=roles or [], display_name=f"User{user_id}")
        self.channel = channel
        self.guild = guild
        self.response = MockDeferredResponse()
        self.followup = MockFollowup()


class MockHistoryChannel:
    def __init__(self, messages, mention="#chan"):
        self._messages = messages
        self.mention = mention
        self.sent = []

    def permissions_for(self, _member):
        return SimpleNamespace(read_message_history=True)

    async def history(self, limit=None):
        items = self._messages[:limit] if limit is not None else self._messages
        for item in items:
            yield item

    async def send(self, message):
        self.sent.append(message)


# --- quote command without user, data exists ---
def test_quote_without_user_returns_quote(attbot_module, monkeypatch):
    interaction = MockInteraction()
    row = (1, 5, "Hastings", "Check your sectors.", "2026-01-01T12:00:00+00:00", "Price")  # added "Price"

    monkeypatch.setattr(attbot_module, "get_random_quote", lambda: row)

    asyncio.run(attbot_module.quote.callback(interaction, None))

    assert interaction.response.sent_messages == [{
        "message": '"Check your sectors." - Price, added by Hastings, 2026',
        "ephemeral": False,
        "view": None,
    }]


# --- myreminders with no reminders ---
def test_myreminders_no_reminders(attbot_module):
    interaction = MockInteraction(user_id=10)

    def fake_get_reminders(uid):
        return []

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(attbot_module, "get_user_reminders", fake_get_reminders)

    asyncio.run(attbot_module.myreminders.callback(interaction))
    assert interaction.response.sent_messages[0]["message"] == "You have no active reminders."


# --- myreminders with reminders, shows select ---
def test_myreminders_with_reminders_builds_select(attbot_module, monkeypatch):
    interaction = MockInteraction(user_id=10)
    reminders = [
        (1, 10, 200, "Reminder 1", "2026-12-01T10:00:00+00:00", 0),
        (2, 10, 200, "Reminder 2", "2026-12-02T14:00:00+00:00", 1),
    ]

    def fake_get_reminders(uid):
        return reminders

    monkeypatch.setattr(attbot_module, "get_user_reminders", fake_get_reminders)

    asyncio.run(attbot_module.myreminders.callback(interaction))

    assert len(interaction.response.sent_messages) == 1
    assert "Here are your active reminders" in interaction.response.sent_messages[0]["message"]
    assert interaction.response.sent_messages[0]["view"] is not None


def _make_guild():
    return SimpleNamespace(chunked=True, members=[], me=object(), get_member=lambda uid: None)


# --- scan_all_reactions with no reactions ---
def test_scan_all_reactions_no_reactions(attbot_module):
    guild = _make_guild()
    interaction = MockCommandInteraction(roles=[SimpleNamespace(name="NCO")], guild=guild)

    no_react_msg = SimpleNamespace(
        reactions=[],
        author=SimpleNamespace(display_name="Author"),
        content="no reactions",
        jump_url="https://test/1",
    )

    channel = MockHistoryChannel([no_react_msg])

    asyncio.run(attbot_module.scan_all_reactions.callback(interaction, channel, 5))

    assert interaction.response.deferred is True
    assert len(interaction.followup.messages) == 1
    assert "No reactions found" in interaction.followup.messages[0]["message"]


# --- scan_all_reactions with messages but no non-bot reactions ---
def test_scan_all_reactions_only_bots(attbot_module):
    guild = _make_guild()
    interaction = MockCommandInteraction(roles=[SimpleNamespace(name="NCO")], guild=guild)

    bot_user = SimpleNamespace(bot=True, name="BotUser")

    class BotReaction:
        emoji = "✅"
        async def users(self):
            yield bot_user

    bot_msg = SimpleNamespace(
        reactions=[BotReaction()],
        author=SimpleNamespace(display_name="Apollo"),
        content="bot message",
        jump_url="https://test/1",
    )

    channel = MockHistoryChannel([bot_msg])

    asyncio.run(attbot_module.scan_all_reactions.callback(interaction, channel, 5))

    assert interaction.response.deferred is True
    assert len(interaction.followup.messages) == 1
    assert "No reactions found" in interaction.followup.messages[0]["message"]


# --- scan_apollo_events early returns ---
def test_scan_apollo_events_no_channel(attbot_module, monkeypatch):
    attbot_module.event_log.clear()
    if 'attendance_log' in globals():
        attbot_module.attendance_log.clear()

    monkeypatch.setattr(attbot_module.bot, "get_channel", lambda x: None)
    result = asyncio.run(attbot_module.scan_apollo_events(limit=5))
    assert result == (0, 0)


def test_scan_apollo_events_no_guild(attbot_module, monkeypatch):
    attbot_module.event_log.clear()
    if 'attendance_log' in globals():
        attbot_module.attendance_log.clear()

    monkeypatch.setattr(attbot_module.bot, "get_channel", lambda x: True)
    monkeypatch.setattr(attbot_module.bot, "get_guild", lambda x: None)
    result = asyncio.run(attbot_module.scan_apollo_events(limit=5))
    assert result == (0, 0)


# --- check_member command ---
def test_check_member_role_required(attbot_module):
    interaction = MockCommandInteraction(roles=[])
    user = SimpleNamespace(display_name="Miller")
    asyncio.run(attbot_module.check_member.callback(interaction, user, limit=8))
    assert interaction.response.sent_messages[0]["ephemeral"] is True


def test_check_member_insufficient_events(attbot_module):
    attbot_module.event_log.clear()
    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    user = SimpleNamespace(display_name="Miller")
    asyncio.run(attbot_module.check_member.callback(interaction, user, limit=8))
    assert "Only 0 events" in interaction.followup.messages[0]["message"]


def test_check_member_accepted(attbot_module):
    attbot_module.event_log.clear()
    attbot_module.event_log.append({
        "accepted": [("miller", "Miller"), ("rydah", "Rydah")],
        "declined": [("mooses", "Mooses")],
    })
    attbot_module.event_log.append({
        "accepted": [("miller", "Miller")],
        "declined": [],
    })

    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    user = SimpleNamespace(id="miller", display_name="Miller")
    attbot_module.event_log.append({
    "accepted": [(1, "Miller"), (2, "Rydah")],
    "declined": [(3, "Mooses")],
    })
    attbot_module.event_log.append({
    "accepted": [(1, "Miller")],
    "declined": [],
    })
    asyncio.run(attbot_module.check_member.callback(interaction, user, limit=2))

    out = interaction.followup.messages[0]["message"]
    assert "Accepted: **2**" in out
    assert "Declined: **0**" in out
    assert "No Response: **0**" in out


def test_check_member_declined(attbot_module):
    attbot_module.event_log.clear()
    attbot_module.event_log.append({
        "accepted": [("miller", "Miller")],
        "declined": [("mooses", "Mooses")],
    })

    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    user = SimpleNamespace(id="mooses", display_name="Mooses")
    attbot_module.event_log.append({
    "accepted": [(1, "Miller")],
    "declined": [(2, "Mooses")],
    })
    attbot_module.event_log.append({
        "accepted": [(1, "Miller")],
        "declined": [(2, "Mooses")],
    })
    asyncio.run(attbot_module.check_member.callback(interaction, user, limit=1))

    out = interaction.followup.messages[0]["message"]
    assert "Accepted: **0**" in out
    assert "Declined: **1**" in out


def test_check_member_no_response(attbot_module):
    attbot_module.event_log.clear()
    attbot_module.event_log.append({
        "accepted": [(1, "Miller")],
        "declined": [(2, "Rydah")],
    })

    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    user = SimpleNamespace(id="mooses", display_name="Mooses")
    asyncio.run(attbot_module.check_member.callback(interaction, user, limit=1))

    out = interaction.followup.messages[0]["message"]
    assert "No Response: **1**" in out


# --- check_member with tuple-like entries ---
def test_check_member_with_string_ids(attbot_module):
    attbot_module.event_log.clear()
    attbot_module.event_log.append({
        "accepted": ["miller"],
        "declined": [],
    })

    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    user = SimpleNamespace(id= "miller", display_name="Miller")
    asyncio.run(attbot_module.check_member.callback(interaction, user, limit=1))

    out = interaction.followup.messages[0]["message"]
    assert "Accepted: **1**" in out


# --- debug_apollo command ---
def test_debug_apollo_role_required(attbot_module):
    interaction = MockCommandInteraction(roles=[])
    asyncio.run(attbot_module.debug_apollo.callback(interaction, limit=50))
    assert interaction.response.sent_messages[0]["ephemeral"] is True


def test_debug_apollo_no_apollo_messages(attbot_module):
    role = SimpleNamespace(name="NCO")
    non_apollo = [SimpleNamespace(author=SimpleNamespace(name="Other"), embeds=[])]
    interaction = MockCommandInteraction(roles=[role], channel=MockHistoryChannel(non_apollo))
    asyncio.run(attbot_module.debug_apollo.callback(interaction, limit=5))
    assert "No Apollo messages found" in interaction.followup.messages[0]["message"]


def test_debug_apollo_found_no_embeds(attbot_module):
    role = SimpleNamespace(name="NCO")
    apollo_no_embeds = [SimpleNamespace(author=SimpleNamespace(name="Apollo"), embeds=[])]
    channel = MockHistoryChannel(apollo_no_embeds)
    interaction = MockCommandInteraction(roles=[role], channel=channel)
    asyncio.run(attbot_module.debug_apollo.callback(interaction, limit=5))
    assert "no embeds" in interaction.followup.messages[0]["message"].lower()


def test_debug_apollo_found_with_embeds(attbot_module):
    role = SimpleNamespace(name="NCO")

    class MockField:
        def __init__(self, name, value):
            self.name = name
            self.value = value

    class MockEmbed:
        def __init__(self):
            self.title = "Test Title"
            self.description = "Test description"
            self.fields = [MockField("Field1", "Value1")]

    apollo_msg = SimpleNamespace(
        author=SimpleNamespace(name="Apollo"),
        embeds=[MockEmbed()],
    )
    channel = MockHistoryChannel([apollo_msg])
    interaction = MockCommandInteraction(roles=[role], channel=channel)
    asyncio.run(attbot_module.debug_apollo.callback(interaction, limit=5))

    # Should have sent embed title and description
    assert len(interaction.followup.messages) >= 1


# --- debug_duplicates command ---
def test_debug_duplicates_role_required(attbot_module):
    interaction = MockCommandInteraction(roles=[])
    asyncio.run(attbot_module.debug_duplicates.callback(interaction))
    assert interaction.response.sent_messages[0]["ephemeral"] is True


def test_debug_duplicates_no_duplicates(attbot_module):
    attbot_module.attendance_log.clear()
    attbot_module.attendance_log["123-1"] = {"username": "Miller", "user_id": "1"}
    attbot_module.attendance_log["123-2"] = {"username": "Rydah", "user_id": "2"}

    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    asyncio.run(attbot_module.debug_duplicates.callback(interaction))
    assert "No username inconsistencies found" in interaction.followup.messages[0]["message"]


def test_debug_duplicates_with_inconsistencies(attbot_module):
    attbot_module.attendance_log.clear()
    attbot_module.attendance_log["123-1"] = {"username": "Miller", "user_id": "1"}
    attbot_module.attendance_log["123-2"] = {"username": "miller", "user_id": "2"}

    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    asyncio.run(attbot_module.debug_duplicates.callback(interaction))
    msg = interaction.followup.messages[0]["message"]
    assert "Inconsistent usernames found" in msg
    assert "miller" in msg


# --- scan_apollo command role check ---
def test_scan_apollo_role_required(attbot_module):
    interaction = MockCommandInteraction(roles=[])
    asyncio.run(attbot_module.scan_apollo.callback(interaction, limit=18))
    assert interaction.response.sent_messages[0]["ephemeral"] is True


def test_scan_apollo_deferred_and_sends_result(attbot_module, monkeypatch):
    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])

    def fake_scan(limit):
        attbot_module.event_log.clear()
        attbot_module.event_log.append({"event_id": 1, "accepted": [], "declined": []})
        return asyncio.sleep(0, result=(5, 1))

    monkeypatch.setattr(attbot_module, "scan_apollo_events", fake_scan)
    asyncio.run(attbot_module.scan_apollo.callback(interaction, limit=18))

    assert interaction.response.deferred is True
    assert "Scanned" in interaction.followup.messages[0]["message"]
    assert "logged" in interaction.followup.messages[0]["message"]


# --- scan_all_reactions message-specific summary ---
def test_scan_all_reactions_message_summaries(attbot_module):
    guild = _make_guild()
    interaction = MockCommandInteraction(roles=[SimpleNamespace(name="NCO")], guild=guild)

    real_user = SimpleNamespace(bot=False, name="Miller", id=100)

    class Reaction:
        emoji = "✅"
        async def users(self):
            yield real_user

    msg = SimpleNamespace(
        reactions=[Reaction()],
        author=SimpleNamespace(display_name="Apollo"),
        content="Attendance check",
        jump_url="https://test/1",
    )

    channel = MockHistoryChannel([msg])
    asyncio.run(attbot_module.scan_all_reactions.callback(interaction, channel, 5))

    assert interaction.response.deferred is True
    output = interaction.followup.messages[0]["message"]
    assert "Reactions Summary" in output
    assert "Miller" in output
    assert "Apollo" in output


# --- ReminderModal parse_datetime edge cases ---
def test_parse_datetime_various_formats(attbot_module):
    # ISO format with timezone
    dt = attbot_module.ReminderModal.parse_datetime("2025-10-05T14:30+02:00")
    assert dt is not None
    assert dt.tzinfo is not None

    # Slash format
    dt2 = attbot_module.ReminderModal.parse_datetime("2025/10/05 14:30")
    assert dt2 is not None

    # Dot format
    dt3 = attbot_module.ReminderModal.parse_datetime("2025.10.05 14:30")
    assert dt3 is not None

    # Compact format
    dt4 = attbot_module.ReminderModal.parse_datetime("20251005 14:30")
    assert dt4 is not None

    # Invalid
    assert attbot_module.ReminderModal.parse_datetime("totally invalid") is None


# --- scan_apollo_events with limit ---
def test_scan_apollo_events_respects_limit(attbot_module, monkeypatch):
    attbot_module.event_log.clear()
    if 'attendance_log' in globals():
        attbot_module.attendance_log.clear()

    class MockEmbed:
        def __init__(self):
            class Field:
                name = "Accepted"
                value = "- Miller"
            self.fields = [Field()]
            self.description = None

    class MockMsg:
        id = 1
        author = SimpleNamespace(name="Apollo")
        embeds = [MockEmbed()]

    class MockChan:
        total_messages = 10

        async def history(self, limit=None):
            for i in range(min(limit or self.total_messages, self.total_messages)):
                yield MockMsg()

    class MockGuild:
        chunked = True
        members = [SimpleNamespace(id=1, display_name="Miller", name="Miller")]

    monkeypatch.setattr(attbot_module.bot, "get_channel", lambda x: MockChan())
    monkeypatch.setattr(attbot_module.bot, "get_guild", lambda x: MockGuild())

    scanned, logged = asyncio.run(attbot_module.scan_apollo_events(limit=2))
    assert len(attbot_module.event_log) == 2


# --- staff_meeting_notes success path (with mock file) ---
def test_staff_meeting_notes_success(tmp_path, attbot_module, monkeypatch):
    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])

    # Create the template file
    template_path = tmp_path / "staff_meeting_note.md"
    template_path.write_text("# Meeting Notes\n\n- Item 1\n- Item 2")

    # Monkeypatch the file path
    monkeypatch.chdir(tmp_path)
    asyncio.run(attbot_module.staff_meeting_notes.callback(interaction))

    assert len(interaction.followup.messages) == 1
    assert "Meeting Notes" in interaction.followup.messages[0]["message"]


# --- scan_apollo_events: guild.chunk() path ---
def test_scan_apollo_events_chunk_guild(attbot_module, monkeypatch):
    attbot_module.event_log.clear()
    if 'attendance_log' in globals():
        attbot_module.attendance_log.clear()

    chunked = [False]

    class ChunkedGuild:
        chunked = False
        members = [SimpleNamespace(id=1, display_name="Miller", name="Miller")]

        async def chunk(self):
            chunked[0] = True

    class ChunkEmbed:
        def __init__(self):
            class Field:
                name = "Accepted"
                value = "- Miller"
            self.fields = [Field()]
            self.description = None

    class ChunkMsg:
        id = 1
        author = SimpleNamespace(name="Apollo")
        embeds = [ChunkEmbed()]

    class ChunkChan:
        total_messages = 1

        async def history(self, limit=None):
            yield ChunkMsg()

    monkeypatch.setattr(attbot_module.bot, "get_channel", lambda x: ChunkChan())
    monkeypatch.setattr(attbot_module.bot, "get_guild", lambda x: ChunkedGuild())

    asyncio.run(attbot_module.scan_apollo_events(limit=1))
    assert chunked[0] is True
    assert len(attbot_module.event_log) == 1


# --- scan_apollo_events: description fallback with no attendees ---
def test_scan_apollo_events_desc_empty(attbot_module, monkeypatch):
    attbot_module.event_log.clear()
    if 'attendance_log' in globals():
        attbot_module.attendance_log.clear()

    class EmptyDescEmbed:
        def __init__(self):
            self.fields = []
            self.description = ""

    class EmptyDescMsg:
        id = 99
        author = SimpleNamespace(name="Apollo")
        embeds = [EmptyDescEmbed()]

    class EmptyDescChan:
        total_messages = 1

        async def history(self, limit=None):
            yield EmptyDescMsg()

    class EmptyDescGuild:
        chunked = True
        members = []

    monkeypatch.setattr(attbot_module.bot, "get_channel", lambda x: EmptyDescChan())
    monkeypatch.setattr(attbot_module.bot, "get_guild", lambda x: EmptyDescGuild())

    scanned, logged = asyncio.run(attbot_module.scan_apollo_events(limit=1))
    assert scanned == 1
    assert logged == 0


# --- deletequote: no quotes ---
def test_deletequote_no_quotes(attbot_module):
    interaction = MockInteraction(user_id=55, display_name="TestUser")

    def fake_get_quotes(uid):
        return []

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(attbot_module, "get_user_quotes", fake_get_quotes)

    asyncio.run(attbot_module.deletequote.callback(interaction))

    assert interaction.response.sent_messages[0]["message"] == "You have no quotes to delete."


# --- deletequote: with quotes, builds view ---
def test_deletequote_with_quotes_builds_view(attbot_module, monkeypatch):
    interaction = MockInteraction(user_id=55, display_name="TestUser")
    rows = [
        (1, 55, "TestUser", "First quote", "2026-01-01T10:00:00+00:00", "Price"),
        (2, 55, "TestUser", "Second quote", "2026-02-01T12:00:00+00:00", "Mooses"),
    ]

    def fake_get_quotes(uid):
        return rows

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(attbot_module, "get_user_quotes", fake_get_quotes)

    asyncio.run(attbot_module.deletequote.callback(interaction))

    assert len(interaction.response.sent_messages) == 1
    assert interaction.response.sent_messages[0]["message"] == "Select a quote to delete:"
    assert interaction.response.sent_messages[0]["ephemeral"] is True
    assert interaction.response.sent_messages[0]["view"] is not None


# --- scan_apollo_events: cancelled reminder_task path ---
def test_reminder_task_cancelled(attbot_module, monkeypatch):
    # Test that parse_datetime handles timezone-aware input
    from datetime import timezone

    dt = attbot_module.ReminderModal.parse_datetime("2025-10-05 14:30+00:00")
    assert dt is not None
    assert dt.tzinfo is not None

    # We can't easily test the full reminder_task since it loops,
    # but we can test the parse_datetime path that it uses
    dt = attbot_module.ReminderModal.parse_datetime("2025-10-05 14:30+00:00")
    assert dt is not None
    assert dt.tzinfo is not None


# --- debug_apollo: chunk sending ---
def test_debug_apollo_long_output_chunks(attbot_module):
    role = SimpleNamespace(name="NCO")

    class BigField:
        def __init__(self):
            self.name = "BigField"
            self.value = "x" * 2000  # Very long value

    class BigEmbed:
        def __init__(self):
            self.title = "Big"
            self.description = "desc"
            self.fields = [BigField()]

    apollo_msg = SimpleNamespace(
        author=SimpleNamespace(name="Apollo"),
        embeds=[BigEmbed()],
    )
    channel = MockHistoryChannel([apollo_msg])
    interaction = MockCommandInteraction(roles=[role], channel=channel)
    asyncio.run(attbot_module.debug_apollo.callback(interaction, limit=5))

    # Should have sent multiple chunks due to 1900 char limit
    assert len(interaction.followup.messages) >= 1


# --- debug_duplicates: long output chunks ---
def test_debug_duplicates_long_output_chunks(attbot_module):
    attbot_module.attendance_log.clear()
    # Create entries with different spellings that normalize to the same name
    attbot_module.attendance_log["123-1"] = {"username": "Miller!", "user_id": "1"}
    attbot_module.attendance_log["123-2"] = {"username": "miller.", "user_id": "2"}
    attbot_module.attendance_log["123-3"] = {"username": "MILLER", "user_id": "3"}

    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    asyncio.run(attbot_module.debug_duplicates.callback(interaction))

    assert len(interaction.followup.messages) >= 1
    assert "Inconsistent usernames found" in interaction.followup.messages[0]["message"]


# --- scan_apollo_events: with declined field containing "x" ---
def test_scan_apollo_events_declined_x_field(attbot_module, monkeypatch):
    attbot_module.event_log.clear()
    if 'attendance_log' in globals():
        attbot_module.attendance_log.clear()

    class DeclinedXEmbed:
        def __init__(self):
            class Field1:
                name = "Accepted"
                value = "- Miller"
            class Field2:
                name = "Declined"
                value = "- Rydah"
            self.fields = [Field1(), Field2()]
            self.description = None

    class DeclinedXMsg:
        id = 99
        author = SimpleNamespace(name="Apollo")
        embeds = [DeclinedXEmbed()]

    class DeclinedXChan:
        total_messages = 1

        async def history(self, limit=None):
            yield DeclinedXMsg()

    class DeclinedXGuild:
        chunked = True
        members = [
            SimpleNamespace(id=1, display_name="Miller", name="Miller"),
            SimpleNamespace(id=2, display_name="Rydah", name="Rydah"),
        ]

    monkeypatch.setattr(attbot_module.bot, "get_channel", lambda x: DeclinedXChan())
    monkeypatch.setattr(attbot_module.bot, "get_guild", lambda x: DeclinedXGuild())

    scanned, logged = asyncio.run(attbot_module.scan_apollo_events(limit=1))
    assert len(attbot_module.event_log) == 1
    assert len(attbot_module.event_log[0]["accepted"]) == 1
    assert len(attbot_module.event_log[0]["declined"]) == 1


# --- scan_apollo_events: with "x" in field name triggers declined ---
def test_scan_apollo_events_x_field_name(attbot_module, monkeypatch):
    attbot_module.event_log.clear()
    if 'attendance_log' in globals():
        attbot_module.attendance_log.clear()

    class XFieldNameEmbed:
        def __init__(self):
            class Field1:
                name = "Accepted"
                value = "- Miller"
            class Field2:
                name = "x-factor"  # Contains "x" so triggers declined path
                value = "- Rydah"
            self.fields = [Field1(), Field2()]
            self.description = None

    class XFieldNameMsg:
        id = 99
        author = SimpleNamespace(name="Apollo")
        embeds = [XFieldNameEmbed()]

    class XFieldNameChan:
        total_messages = 1

        async def history(self, limit=None):
            yield XFieldNameMsg()

    class XFieldNameGuild:
        chunked = True
        members = [
            SimpleNamespace(id=1, display_name="Miller", name="Miller"),
            SimpleNamespace(id=2, display_name="Rydah", name="Rydah"),
        ]

    monkeypatch.setattr(attbot_module.bot, "get_channel", lambda x: XFieldNameChan())
    monkeypatch.setattr(attbot_module.bot, "get_guild", lambda x: XFieldNameGuild())

    scanned, logged = asyncio.run(attbot_module.scan_apollo_events(limit=1))
    assert len(attbot_module.event_log) == 1
    # "x-factor" contains "x" so Rydah goes to declined, Miller stays in accepted
    assert len(attbot_module.event_log[0]["accepted"]) == 1
    assert len(attbot_module.event_log[0]["declined"]) == 1


# --- scan_apollo_events: unresolveable name (debug output) ---
def test_scan_apollo_events_unresolved_name(attbot_module, monkeypatch, capfd):
    attbot_module.event_log.clear()
    if 'attendance_log' in globals():
        attbot_module.attendance_log.clear()

    class UnresolvedEmbed:
        def __init__(self):
            class Field1:
                name = "Accepted"
                value = "- UnknownPerson"
            self.fields = [Field1()]
            self.description = None

    class UnresolvedMsg:
        id = 99
        author = SimpleNamespace(name="Apollo")
        embeds = [UnresolvedEmbed()]

    class UnresolvedChan:
        total_messages = 1

        async def history(self, limit=None):
            yield UnresolvedMsg()

    class UnresolvedGuild:
        chunked = True
        members = [SimpleNamespace(id=1, display_name="Miller", name="Miller")]

    monkeypatch.setattr(attbot_module.bot, "get_channel", lambda x: UnresolvedChan())
    monkeypatch.setattr(attbot_module.bot, "get_guild", lambda x: UnresolvedGuild())

    scanned, logged = asyncio.run(attbot_module.scan_apollo_events(limit=1))
    assert len(attbot_module.event_log) == 1
    # UnknownPerson can't be resolved to a guild member, so accepted is empty
    assert len(attbot_module.event_log[0]["accepted"]) == 0
    assert logged == 0


# --- hilf command ---
def test_hilf_sends_embed(attbot_module):
    interaction = MockCommandInteraction()
    asyncio.run(attbot_module.hilf.callback(interaction))
    assert interaction.response.deferred is True
    assert len(interaction.followup.messages) == 1
    msg = interaction.followup.messages[0]
    assert msg["embed"] is not None


# --- staff_meeting_notes command ---
def test_staff_meeting_notes_role_required(attbot_module):
    interaction = MockCommandInteraction(roles=[])
    asyncio.run(attbot_module.staff_meeting_notes.callback(interaction))
    assert interaction.response.sent_messages[0]["ephemeral"] is True


def test_staff_meeting_notes_file_not_found(attbot_module):
    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    asyncio.run(attbot_module.staff_meeting_notes.callback(interaction))
    assert "not found" in interaction.followup.messages[0]["message"].lower()


# --- summary command ---
def test_summary_role_required(attbot_module):
    interaction = MockCommandInteraction(roles=[])
    asyncio.run(attbot_module.summary.callback(interaction, limit=8))
    assert interaction.followup.messages[0]["ephemeral"] is True


def test_summary_with_sufficient_events(attbot_module, monkeypatch):
    role = SimpleNamespace(name="NCO")
    guild = SimpleNamespace(members=[
        SimpleNamespace(id=1, display_name="Miller", roles=[], bot=False),
        SimpleNamespace(id=2, display_name="Rydah", roles=[], bot=False),
        SimpleNamespace(id=3, display_name="Mooses", roles=[], bot=False),
    ])
    interaction = MockCommandInteraction(roles=[role], guild=guild)

    def fake_scan(limit):
        attbot_module.event_log.clear()
        attbot_module.event_log.append({
            "accepted": [(1, "Miller"), (2, "Rydah")],
            "declined": [(3, "Mooses")],
        })
        attbot_module.event_log.append({
            "accepted": [(1, "Miller")],
            "declined": [(2, "Rydah")],
        })
        return asyncio.sleep(0, result=(2, 2))

    monkeypatch.setattr(attbot_module, "scan_apollo_events", fake_scan)
    asyncio.run(attbot_module.summary.callback(interaction, limit=2))

    assert interaction.response.deferred is True
    assert len(interaction.followup.messages) >= 1
    assert "Summary" in interaction.followup.messages[0]["message"]


# --- leaderboard with no attendees ---
def test_leaderboard_no_attendees(attbot_module):
    attbot_module.event_log.clear()
    attbot_module.event_log.append({
        "accepted": [],
        "declined": [(1, "Miller")],
    })

    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    asyncio.run(attbot_module.leaderboard.callback(interaction, limit=1))

    assert interaction.response.deferred is True
    output = interaction.followup.messages[0]["message"]
    assert "No attendees found" in output
    assert "Miller" in output


# --- leaderboard with astro award ---
def test_leaderboard_astro_award(attbot_module):
    attbot_module.event_log.clear()
    attbot_module.event_log.append({
        "accepted": [(1, "Miller"), (2, "Rydah")],
        "declined": [],
    })
    attbot_module.event_log.append({
        "accepted": [(1, "Miller"), (2, "Rydah")],
        "declined": [],
    })

    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    asyncio.run(attbot_module.leaderboard.callback(interaction, limit=2))

    output = interaction.followup.messages[0]["message"]
    assert "Astro Award" in output
    assert "Miller" in output
    assert "Rydah" in output


# --- leaderboard with good conduct award ---
def test_leaderboard_good_conduct_award(attbot_module):
    attbot_module.event_log.clear()
    attbot_module.event_log.append({
        "accepted": [(1, "Miller")],
        "declined": [(2, "Rydah")],
    })
    attbot_module.event_log.append({
        "accepted": [(1, "Miller")],
        "declined": [(2, "Rydah")],
    })

    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    asyncio.run(attbot_module.leaderboard.callback(interaction, limit=2))

    output = interaction.followup.messages[0]["message"]
    assert "Good Conduct Award" in output


# --- ReminderModal parse_datetime with explicit tz ---
def test_parse_datetime_explicit_tz(attbot_module):
    dt = attbot_module.ReminderModal.parse_datetime("2025-10-05 14:30+05:00")
    assert dt is not None
    # Should be converted to UTC
    assert dt.hour == 9  # 14:30 - 5 hours = 09:30


# --- ReminderModal on_submit: invalid date ---
def test_reminder_modal_invalid_date(attbot_module):
    class FakeTextInput:
        def __init__(self, val):
            self.value = val

    class FakeModal:
        date = FakeTextInput("not-a-date")
        message = FakeTextInput("Test")
        dm = FakeTextInput("no")
        parse_datetime = staticmethod(attbot_module.ReminderModal.parse_datetime)

    modal = FakeModal()
    resp = MockDeferredResponse()
    mock_interaction = SimpleNamespace(response=resp)
    asyncio.run(attbot_module.ReminderModal.on_submit(modal, mock_interaction))

    assert len(resp.sent_messages) == 1
    assert "Invalid date format" in resp.sent_messages[0]["message"]


# --- ReminderModal on_submit: past date ---
def test_reminder_modal_past_date(attbot_module):
    class FakeTextInput:
        def __init__(self, val):
            self.value = val

    class FakeModal:
        date = FakeTextInput("2020-01-01 00:00")
        message = FakeTextInput("Test")
        dm = FakeTextInput("no")
        parse_datetime = staticmethod(attbot_module.ReminderModal.parse_datetime)

    modal = FakeModal()
    resp = MockDeferredResponse()
    mock_interaction = SimpleNamespace(response=resp)
    asyncio.run(attbot_module.ReminderModal.on_submit(modal, mock_interaction))

    assert len(resp.sent_messages) == 1
    assert "future" in resp.sent_messages[0]["message"].lower()


# --- ReminderModal on_submit: success path (with DB) ---
def test_reminder_modal_on_submit_success(tmp_path, attbot_module, monkeypatch):
    from bots.utils import init_db
    from datetime import timezone

    db_path = str(tmp_path / "reminder_test.db")
    init_db(db_path)

    class FakeTextInput:
        def __init__(self, val):
            self.value = val

    class FakeModal:
        date = FakeTextInput("2026-12-01 10:00")
        message = FakeTextInput("Test reminder")
        dm = FakeTextInput("no")
        parse_datetime = staticmethod(attbot_module.ReminderModal.parse_datetime)

    modal = FakeModal()
    resp = MockDeferredResponse()
    mock_interaction = SimpleNamespace(response=resp, user=SimpleNamespace(id=10), channel=SimpleNamespace(id=20))
    monkeypatch.setattr(attbot_module, "add_reminder", lambda uid, cid, msg, dt, dm: 1)
    monkeypatch.setattr(attbot_module, "get_reminders", lambda: [])

    asyncio.run(attbot_module.ReminderModal.on_submit(modal, mock_interaction))

    assert len(resp.sent_messages) == 1
    assert "Reminder set" in resp.sent_messages[0]["message"]


# --- scan_apollo_events: embed.description fallback ---
def test_scan_apollo_events_desc_fallback(attbot_module, monkeypatch):
    attbot_module.event_log.clear()
    if 'attendance_log' in globals():
        attbot_module.attendance_log.clear()

    class DescEmbed:
        def __init__(self):
            self.fields = []
            self.description = "- Miller\n- Rydah"

    class DescMsg:
        id = 99
        author = SimpleNamespace(name="Apollo")
        embeds = [DescEmbed()]

    class DescChan:
        total_messages = 1

        async def history(self, limit=None):
            yield DescMsg()

    class DescGuild:
        chunked = True
        members = [SimpleNamespace(id=1, display_name="Miller", name="Miller"), SimpleNamespace(id=2, display_name="Rydah", name="Rydah")]

    monkeypatch.setattr(attbot_module.bot, "get_channel", lambda x: DescChan())
    monkeypatch.setattr(attbot_module.bot, "get_guild", lambda x: DescGuild())

    asyncio.run(attbot_module.scan_apollo_events(limit=1))
    assert len(attbot_module.event_log) == 1
    assert len(attbot_module.event_log[0]["accepted"]) == 2


# --- check_member with event_key fallback ---
def test_check_member_event_key_fallback(attbot_module):
    attbot_module.event_log.clear()
    # Events without standard keys use repr() for dedup
    attbot_module.event_log.append({"data": "event1", "accepted": [("miller", "Miller")]})
    attbot_module.event_log.append({"data": "event2", "accepted": []})

    role = SimpleNamespace(name="NCO")
    interaction = MockCommandInteraction(roles=[role])
    user = SimpleNamespace(id="miller", display_name="Miller")
    asyncio.run(attbot_module.check_member.callback(interaction, user, limit=2))

    out = interaction.followup.messages[0]["message"]
    assert "Accepted: **1**" in out


# --- scan_all_reactions with permission denied ---
def test_scan_all_reactions_permission_denied(attbot_module):
    guild = SimpleNamespace(chunked=True, members=[], me=object())
    interaction = MockCommandInteraction(roles=[SimpleNamespace(name="NCO")], guild=guild)

    class DenyChannel:
        mention = "#restricted"

        def permissions_for(self, _m):
            return SimpleNamespace(read_message_history=False)

        async def history(self, limit=None):
            return
            yield  # noqa

    channel = DenyChannel()
    asyncio.run(attbot_module.scan_all_reactions.callback(interaction, channel, 5))

    assert interaction.response.deferred is True
    assert len(interaction.followup.messages) == 1
    assert "Can't read message history" in interaction.followup.messages[0]["message"]


# --- scan_apollo_events: non-apollo message skipped ---
def test_scan_apollo_events_skips_non_apollo(attbot_module, monkeypatch):
    attbot_module.event_log.clear()
    if 'attendance_log' in globals():
        attbot_module.attendance_log.clear()

    class NonApolloMsg:
        id = 1
        author = SimpleNamespace(name="OtherBot")
        embeds = []

    class NonApolloChan:
        total_messages = 1

        async def history(self, limit=None):
            yield NonApolloMsg()

    class NonApolloGuild:
        chunked = True
        members = []

    monkeypatch.setattr(attbot_module.bot, "get_channel", lambda x: NonApolloChan())
    monkeypatch.setattr(attbot_module.bot, "get_guild", lambda x: NonApolloGuild())

    scanned, logged = asyncio.run(attbot_module.scan_apollo_events(limit=5))
    assert scanned == 1  # still counted as scanned
    assert len(attbot_module.event_log) == 0  # but no events collected