# Testing of mock discord reactions to a bot and mock discord objects

"""This test file, tests for the scan_apollo_events function using mock messages, embeds, users, discord bot, channel and guild, using
    Monekypatch bot methods."""

import pytest
import asyncio
from types import SimpleNamespace # to be used with better testing, maybe.
from bots.attbot import scan_apollo_events, event_log, attendance_log

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
    def __init__(self, id, display_name):
        self.id = id
        self.display_name = display_name

# create mock guild, we want to send the messages in the server as chunks (due to char limit), so set chunked = True
# Then pass in the MockMember, and let the guild class inherit the attributes of the mockmembers, pass in the id and display name (those are attributes)
class MockGuild:
    def __init__(self):
        self.chunked = True
        self.members = [
            MockMember(1, "Miller"),
            MockMember(2, "Rydah"),
            MockMember(3, "Mooses"),
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
@pytest.mark.asyncio
async def test_scan_apollo_events(monkeypatch):

    # first clear the event_log and attendance_log globals
    event_log.clear()
    attendance_log.clear()

    # get the bot file
    from bots import attbot

    # since the real function is using the "bot" module, and the get_channel is a method of it "target_channel = bot.get_channel(int(CHANNEL_ID))"
    # we simulate that with the lambda function so it returns the fake channel_id and guild_id objects we created. 
    # NOTE-- in the real function, get_channel is a method of bot, NOT a function defined in attbot.py so, bot.get_channel()
    monkeypatch.setattr(attbot.bot, "get_channel", lambda x: MockChannel())
    monkeypatch.setattr(attbot.bot, "get_guild", lambda x: MockGuild())

    # then store the scanned and logged events by calling scan_apollo_events, which returns the mock channel and guild, and the guild members and 
    # channel.history (those are attributes of the mockchannel and mockguild objects), then mock messages are yielded, embed parsing runs, event_log
    # and attendance_log gets filled, stops after limit (2 for eg) 
    scanned, logged = await scan_apollo_events(limit=2)

    # then test that only those "limit=2" to test of the actual function's break logic works; 
    # if limit and apollo_events_collected >= limit:
        # break
    assert len(event_log) == 2
    assert logged > 0   # just checking if attendance parsing worked and log_attendance() was triggered