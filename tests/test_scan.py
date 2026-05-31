# Testing of mock discord reactions to a bot and mock discord objects

"""This test file, tests for the scan_apollo_events function using mock messages, embeds, users, discord bot, channel and guild, using
    Monekypatch bot methods."""

import pytest
import asyncio
import importlib
from types import SimpleNamespace # to be used with better testing, maybe.


@pytest.fixture
def attbot_module(monkeypatch):
    monkeypatch.setenv("TOKEN", "test-token")
    monkeypatch.setenv("CHANNEL_ID", "12345678901234567")
    monkeypatch.setenv("GUILD_ID", "12345678901234567")

    import discord.ext.commands as commands
    monkeypatch.setattr(commands.Bot, "run", lambda self, *args, **kwargs: None)

    from bots import attbot
    return importlib.reload(attbot)

# create mock field object, give name and value
class MockField:
    def __init__(self, name, value):
        self.name = name
        self.value = value

# create a mock embed with the embed fields taking in multiple types of names with special characters, whitespace and cases, leave description empty
# also have one of the mock feilds accepted, and one declined
class MockEmbed:
    def __init__(self):
        self.fields = [
            MockField("Accepted", "- Miller\n- Rydah"),
            MockField("Declined", "- Mooses")
        ]
        self.description = None

# mock author for a "user" that posted the message, in this case the user is Apollo, but it can be anything, just make sure the test name reflects the actual
# usecase
class MockAuthor:
    def __init__(self):
        self.name = "Apollo"

# create a mock message, give the msg_id to the method, pass in mock author object and the embed as a list of strings to make both the author and embed
# the attribute of message
class MockMessage:
    def __init__(self, msg_id):
        self.id = msg_id
        self.author = MockAuthor()
        self.embeds = [MockEmbed()]

# mock member to again have the same attribute as the actual discord scenario ie, the user's id and displace_name, pass both to the init
class MockMember:
    def __init__(self, id, display_name, name=None):
        self.id = id
        self.display_name = display_name
        # 'name' is the stable @username (never changes on promotion).
        # Falls back to display_name if not provided, mirroring how Discord
        # members without a separate username would behave.
        self.name = name if name is not None else display_name

# create mock guild, we want to send the messages in the server as chunks (due to char limit), so set chunked = True
# Then pass in the MockMember, and let the guild class inherit the attributes of the mockmembers, pass in the id and display name (those are attributes)
class MockGuild:
    def __init__(self):
        self.chunked = True
        self.members = [
            # display_name is the current nickname (can change on promotion e.g. MSPC/5 -> MSPC/6)
            # name is the stable @username used as fallback in resolve_member
            MockMember(1, "Miller", name="miller_stable"),
            MockMember(2, "Rydah", name="rydah_stable"),
            MockMember(3, "Mooses", name="mooses_stable"),
        ]

# then create a mock channel class, that passes total messages to scan, repects the limit provided and iterates over each message and simulate and async
# generator for us to actually iterate over the messages in discord because in discord;
# Channel.history() -> makes HTTP request -> returns async iterator -> yields real messages
# The actual function has:
    # async for msg in target_channel.history(limit=max_to_scan): so we provide something thats async, is iterable with async, yeilds message-like objects.
class MockChannel:
    def __init__(self, total_messages=10):
        self.total_messages = total_messages

    async def history(self, limit=None):
        count = min(limit or self.total_messages, self.total_messages)
        for i in range(count):
            yield MockMessage(i)


# Now we use Monkeypatch to run asyncronous tests, because normal pytest cant obv run 'await' inside a test, and we want this to run only inside an event loop
# since monkeypatch is a baked in pytest thing, we can use it to allow us to temporarily override attributes at runtime, basically replacing real discord calls
def test_scan_apollo_events(monkeypatch, attbot_module):

    # first clear the event_log and attendance_log globals
    attbot_module.event_log.clear()
    attbot_module.attendance_log.clear()

    # since the real function is using the "bot" module, and the get_channel is a method of it "target_channel = bot.get_channel(int(CHANNEL_ID))"
    # we simulate that with the lambda function so it returns the fake channel_id and guild_id objects we created. 
    # NOTE-- in the real function, get_channel is a method of bot, NOT a function defined in attbot.py so, bot.get_channel()
    monkeypatch.setattr(attbot_module.bot, "get_channel", lambda x: MockChannel())
    monkeypatch.setattr(attbot_module.bot, "get_guild", lambda x: MockGuild())

    # then store the scanned and logged events by calling scan_apollo_events, which returns the mock channel and guild, and the guild members and 
    # channel.history (those are attributes of the mockchannel and mockguild objects), then mock messages are yielded, embed parsing runs, event_log
    # and attendance_log gets filled, stops after limit (2 for eg) 
    scanned, logged = asyncio.run(attbot_module.scan_apollo_events(limit=2))

    # then test that only those "limit=2" to test of the actual function's break logic works; 
    # if limit and apollo_events_collected >= limit:
        # break
    assert len(attbot_module.event_log) == 2
    assert logged > 0   # just checking if attendance parsing worked and log_attendance() was triggered


class MockRole:
    def __init__(self, name):
        self.name = name


class MockDiscordUser:
    def __init__(self, user_id, name, bot=False):
        self.id = user_id
        self.name = name
        self.bot = bot


class MockGuildMember:
    def __init__(self, user_id, display_name):
        self.id = user_id
        self.display_name = display_name


class MockReaction:
    def __init__(self, emoji, users):
        self.emoji = emoji
        self._users = users

    async def users(self):
        for user in self._users:
            yield user


class MockReactionMessage:
    def __init__(self, author_name, content, jump_url, reactions):
        self.author = SimpleNamespace(display_name=author_name)
        self.content = content
        self.jump_url = jump_url
        self.reactions = reactions


class MockResponse:
    def __init__(self):
        self.deferred = False
        self.sent_messages = []

    async def send_message(self, message, ephemeral=False):
        self.sent_messages.append((message, ephemeral))

    async def defer(self, thinking=False):
        self.deferred = thinking


class MockFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, message):
        self.messages.append(message)


class MockReactionGuild:
    def __init__(self):
        self.me = object()
        self._members = {
            1: MockGuildMember(1, "Miller"),
            2: MockGuildMember(2, "Rydah"),
        }

    def get_member(self, user_id):
        return self._members.get(user_id)


class MockReactionChannel:
    def __init__(self, messages, can_read_history=True, mention="#test-channel"):
        self._messages = messages
        self._can_read_history = can_read_history
        self.mention = mention

    def permissions_for(self, _member):
        return SimpleNamespace(read_message_history=self._can_read_history)

    async def history(self, limit=None):
        items = self._messages[:limit] if limit is not None else self._messages
        for msg in items:
            yield msg


class MockInteraction:
    def __init__(self, roles, guild):
        self.user = SimpleNamespace(roles=roles)
        self.guild = guild
        self.response = MockResponse()
        self.followup = MockFollowup()


def test_scan_all_reactions_requires_nco_role(attbot_module):
    interaction = MockInteraction(roles=[], guild=MockReactionGuild())
    channel = MockReactionChannel(messages=[])

    asyncio.run(attbot_module.scan_all_reactions.callback(interaction, channel, 5))

    assert interaction.response.sent_messages == [(
        "You must be an **NCO** to use this command.",
        True,
    )]
    assert interaction.response.deferred is False
    assert interaction.followup.messages == []


def test_scan_all_reactions_summarizes_non_bot_users(attbot_module):
    guild = MockReactionGuild()
    interaction = MockInteraction(roles=[MockRole("NCO")], guild=guild)

    reacting_users = [
        MockDiscordUser(1, "miller_user", bot=False),
        MockDiscordUser(2, "rydah_user", bot=False),
        MockDiscordUser(99, "ExternalUser", bot=False),
        MockDiscordUser(77, "SomeBot", bot=True),
    ]
    message = MockReactionMessage(
        author_name="Apollo",
        content="Attendance check for Thursday op",
        jump_url="https://discord.test/message/1",
        reactions=[MockReaction("✅", reacting_users)],
    )
    channel = MockReactionChannel(messages=[message], can_read_history=True)

    asyncio.run(attbot_module.scan_all_reactions.callback(interaction, channel, 5))

    assert interaction.response.deferred is True
    assert len(interaction.followup.messages) == 1
    output = interaction.followup.messages[0]
    assert "Reactions Summary" in output
    assert "Message by Apollo" in output
    assert "✅ - 3 reaction(s)" in output
    assert "Miller" in output
    assert "Rydah" in output
    assert "ExternalUser" in output
    assert "SomeBot" not in output


def test_scan_all_reactions_handles_missing_history_permission(attbot_module):
    guild = MockReactionGuild()
    interaction = MockInteraction(roles=[MockRole("NCO")], guild=guild)
    channel = MockReactionChannel(messages=[], can_read_history=False, mention="#restricted")

    asyncio.run(attbot_module.scan_all_reactions.callback(interaction, channel, 5))

    assert interaction.response.deferred is True
    assert interaction.followup.messages == ["Can't read message history in #restricted."]