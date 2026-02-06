""" 
This is a unique discord bot that reverse-engineers the closed source event and server management bots using the Discord API, essentially forming a
    closed ecosystem extraction. It scans the activity of other bots in the server by creating a websocket with the hosts, using Discord's Gateway API.
"""


import discord
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from discord.ext import commands
from discord.ui import View, Select
from discord import TextChannel, app_commands, Interaction
from collections import defaultdict
from dateutil import parser
import re
import random
import secrets
import logging
import asyncio 
import sqlite3


from utils import init_db, get_user_reminders, add_reminder, delete_reminder, get_reminders

__version__ = "1.7"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logging.info(f"Starting scanner-bot... v{__version__}")

# Load env variables
load_dotenv()
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
GUILD_ID = os.getenv("GUILD_ID")

if not TOKEN:
    TOKEN = input("Enter your Discord Bot Token: ")


def is_valid_snowflake(s):
    """Returns True if input string is a valid Discord snowflake ID."""

    return bool(re.fullmatch(r"\d{17,20}", s))


if not CHANNEL_ID or not is_valid_snowflake(str(CHANNEL_ID)):

    while True:
        user_input = input("Enter a valid Channel ID (17-20 digits): ")

        if is_valid_snowflake(user_input):
            CHANNEL_ID = int(user_input)
            break

        print("Invalid Channel ID format. Try again.")


if not GUILD_ID or not is_valid_snowflake(GUILD_ID):

    while True:
        user_input = input("Enter a valid Guild ID (17-20 digits): ")

        if is_valid_snowflake(user_input):
            GUILD_ID = user_input
            break

        print("Invalid Guild ID format. Try again.")


# Initialize the discord intent object and set most needed paramters from the docs of "discord" to True
intents = discord.Intents.default()

# Required for commands and reading messages
intents.message_content = True

# obviously, required for reactions, members ids/names and the guild/clan itself
intents.reactions = True
intents.members = True
intents.guilds = True

# needed to receive message + reaction payloads
intents.messages = True

# get the bot commands in a variable with usual/standard prefix
bot = commands.Bot(command_prefix="/", intents=intents)

scheduled_reminders: dict[int, asyncio.Task] = {}
reminders_loaded = False # prevents duplicate scheduling on reconnect

# In-memory log: pseudo_id -> log entry
attendance_log = {}

# Holds data for all of  Apollo events
event_log = []  # Populate this in /scan_apollo command

# Holds data temporarily by scanning member activity
member_data = []

# already logged function that removes duplicates
def already_logged(pseudo_id):
    return pseudo_id in attendance_log


def normalize_name(name: str) -> str:
    """ Using regex, we normalise scanned names to pass into other functions. """

    name = name.lower()
    name = re.sub(r"[^\w\s]", "", name)  # remove punctuation
    name = re.sub(r"\s+", " ", name)     # normalize whitespace
    return name.strip()


def schedule_reminder(reminder_id, user_id, channel_id, message, remind_time, dm):

    """
        Scheduling a reminder to create the reminder task, instead of insertion and deletion on runtime, that creates issues with tables being deleted
        in the db but the actual even still active. 
    """

    # Avoid duplicates
    if reminder_id in scheduled_reminders:
        return

    task = asyncio.create_task(
        reminder_task(reminder_id, user_id, channel_id, message, remind_time, dm)
    )
    scheduled_reminders[reminder_id] = task


@bot.event
async def on_ready():
    """Event syncing function to sync all available commands to deployment environment."""

    global reminders_loaded

    # Info: Bot successfully connected
    logging.info(f"Bot connected as {bot.user}")

    # Debug: Detailed user info (useful for troubleshooting)
    logging.debug(f"Logged in as {bot.user}")

    # call the init function to get the db
    init_db()

    # Only load reminders ONCE per process lifetime, if reminders are not loaded, then for each reminder in the get_reminders utils functions,
    # get that reminder and schedule it, set loaded reminders to True
    if not reminders_loaded:
        for r in get_reminders():
            reminder_id, user_id, channel_id, message, remind_time, dm = r
            schedule_reminder(reminder_id, user_id, channel_id, message, remind_time, dm)
        reminders_loaded = True

    try:
        synced = await bot.tree.sync()

        # check info if commands synced
        logging.info(f"Synced {len(synced)} command(s) successfully")

    except Exception as e:
        # check for syncing fail
        logging.error(f"Error syncing commands: {e}")



async def reminder_task(reminder_id, user_id, channel_id, message, remind_time, dm):

    """ function gets reminder task in iso format and check if there is a dm to be sent to the user to confirm or create a message """

    # We want to try, to try check if there is an existing reminder task in memory
    try:
        try:
            if isinstance(remind_time, str):
                remind_time = parser.isoparse(remind_time)

            # If there is no timezone info, replace the existing reminder with the current UTC of the user who made the task
            if remind_time.tzinfo is None:
                remind_time = remind_time.replace(tzinfo=timezone.utc)

        except Exception as e:
            logging.error(f"Failed to parse remind_time for reminder {reminder_id}: {e}")
            return

        # Accurate long-term waiting, using this while loop, we continuosly check for the time of the reminder to be sent, by finding delta between
        # time of reminder, and time now.
        while True:
            now = datetime.now(timezone.utc)
            remaining = (remind_time - now).total_seconds()

            if remaining <= 0:
                break

            try:
                await asyncio.sleep(min(remaining, 3600))
            except asyncio.CancelledError:
                logging.info(f"Reminder {reminder_id} cancelled during sleep.")
                return

        # Make sure reminder still exists, by checking from the index of the get reminders dictionary on top, if not, then stop function
        if not any(r[0] == reminder_id for r in get_reminders()):
            return

        # Final time sanity check
        now = datetime.now(timezone.utc)
        if now < remind_time - timedelta(seconds=2):
            return

        # Get the user.id in a variable, then check if the user opted for a DM or "in-channel reminder", if it was a dm, then send the dm with the message
        # else get the channel_id the command was made in, and send the reminder there.
        user = await bot.fetch_user(user_id)

        if dm:
            await user.send(f"Reminder: {message}")
        else:
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send(f"{user.mention} ⏰ Reminder: {message}")

        # Once reminder has been executed, call delete reminder function and "cancel.Task" the reminder_id and the users_id from the db
        delete_reminder(reminder_id, user_id)

    except Exception as e:
        logging.exception(f"Unexpected error in reminder_task {reminder_id}: {e}")

    # Finally is a statement in python that ALWAYS executes after the try/except block, no matter if an exception was raised
    finally:
        scheduled_reminders.pop(reminder_id, None)



async def scan_apollo_events(limit: int = 8) -> tuple[int, int]:

    """
    Scans the channel history to collect exactly `limit` Apollo events.
    Returns a tuple: (messages_scanned, attendees_logged)
    """

    scanned_messages = 0
    logged = 0
    max_to_scan = 1000  # upper bound to avoid infinite loops

    event_log.clear()
    if 'attendance_log' in globals():
        attendance_log.clear()

    target_channel = bot.get_channel(int(CHANNEL_ID))
    if not target_channel:
        return (0, 0)

    apollo_events_collected = 0

    async for msg in target_channel.history(limit=max_to_scan):
        scanned_messages += 1

        # Only count Apollo bot messages
        if "Apollo" not in msg.author.name:
            continue

        apollo_events_collected += 1

        attendees, declined = [], []

        for embed in msg.embeds:

            # Accepted
            for field in embed.fields:
                if "accepted" in field.name.lower():
                    for line in field.value.split("\n"):
                        name = line.strip("- ").strip()
                        if name:
                            attendees.append(name)

                # Declined or ❌
                if "declined" in field.name.lower() or "x" in field.name.lower():
                    for line in field.value.split("\n"):
                        name = line.strip("- ").strip()
                        if name:
                            declined.append(name)

            # Fallback: attendees in description
            if embed.description:
                for line in embed.description.split("\n"):
                    if line.strip().startswith("-"):
                        name = line.strip("- ").strip()
                        if name:
                            attendees.append(name)

        # Normalize names
        normalized_attendees = [(normalize_name(name), name) for name in attendees]
        normalized_declined = [(normalize_name(name), name) for name in declined]

        # Log the event
        event_log.append({
            "event_id": msg.id,
            "accepted": normalized_attendees,
            "declined": normalized_declined
        })

        for user_id, pretty in normalized_attendees:
            pseudo_id = f"{msg.id}-{user_id}"
            if not already_logged(pseudo_id):
                log_attendance(user_id, pretty, msg.id)
                logged += 1

        for user_id, pretty in normalized_declined:
            pseudo_id = f"{msg.id}-{user_id}-declined"
            if not already_logged(pseudo_id):
                log_attendance(user_id, pretty, msg.id, response="declined")
                logged += 1

        # Stop early if we've collected enough Apollo events
        if apollo_events_collected >= limit:
            break

    return (scanned_messages, logged)


def log_attendance(user_id, username, event_id, response="accepted"):

    """
    Logs all users who have accepted. Ie, this function allows you to target any specific embed string and capture that response as a formatted
        data structure.
        - Also useful for logging users/reactions without filtering in nested functions, by targeting specific embed parameters of a reactable button.
    """

    normalized_id = normalize_name(user_id)
    pseudo_id = f"{event_id}-{normalized_id}" if response == "accepted" else f"{event_id}-{normalized_id}-declined"

    if pseudo_id not in attendance_log:
        attendance_log[pseudo_id] = {

            "timestamp": datetime.now().isoformat(),
            "user_id": normalized_id,

            # preserve pretty version (username_x becomes server specific 'nickname' eg for milsim clans: pyle -> Pvt G. Pyle)
            "username": username.strip(),
            "event_id": event_id,
            "response": response
        }



"""
--- NOTE --- 
This chunk of comments was for the async payload function, doesnt work for Apollo embeds but DOES if we want to use similar functionality in the future
for normal emoji reactions to messages and log them
-----------------------------------------------------------------------------------------------------------------------------------------------------

# Make an async function for the raw reaction transfer with its payload
    # we need to consider that we have to add the payload for every reaction, and the data we need for that is:
        # 1- the reaction emoji
        # 2- the channel id
        # 3- bot id and member/user id must match

@bot.event
async def on_raw_reaction_add(payload):
    print(f"Detected reaction: '{payload.emoji.name}'")

    if payload.emoji.name != REACTION_EMOJI:
        return
    if payload.channel_id != CHANNEL_ID:
        return
    if payload.user_id == bot.user.id:
        return

    # store the member and "guild" with their corresponding data in simpler vars then:
    guild = bot.get_guild(payload.guild_id)
    member = guild.get_member(payload.user_id)

    # if the member is valid, log their attendance with needed params and print what they attended
    if member:
        log_attendance(member.id, member.name, payload.message_id)
        print(f"{member.name} attended event {payload.message_id}")
-----------------------------------------------------------------------------------------------------------------------------------------------------
"""

# TODO: Set up a command like /post_summary to auto-post attendance summaries at the end of the month in a formatted embed. 
# TODO: Improve /leaderboard by including the event name (if found in embed.title or embed.descriptio) not applicable for our clan (events not named)
# TODO: Command that shows attendance for each member, filterable by member, rank, and timeframe



# debug attendance log
@bot.command()
async def dump_attendance(ctx):

    """ Command dumps the cached global dictionary contents. """

    await ctx.send(f"Current entries: {len(attendance_log)}")


class ReminderModal(discord.ui.Modal):

    """ reminder modal class to forego any kind of user input errors, let them choose within given parameters and not free type the time.
        Method allows users to set a message, date and dm type via modals. """

    # set the message, date and dm modals with hints and ISO format UTC time
    def __init__(self):
        super().__init__(title="Create a Reminder")

        # Define text inputs, use discord's textstyle
        # Define placeholder message for each field ie, message, date and whether to DM or not.

        self.message = discord.ui.TextInput(
            label="Reminder Message",
            style=discord.TextStyle.short,
            placeholder="e.g. mission making meeting!",
            required=True
        )
        self.date = discord.ui.TextInput(
            label="Date & Time (YYYY-MM-DD HH:MM, UTC)",
            style=discord.TextStyle.short,
            placeholder="2025-10-05 14:30",
            required=True
        )
        self.dm = discord.ui.TextInput(
            label="Send as DM? (yes/no)",
            style=discord.TextStyle.short,
            default="no",
            required=True
        )

        # Add the 3 items to modal
        self.add_item(self.message)
        self.add_item(self.date)
        self.add_item(self.dm)

    # Flexible date parser, make it a static method, as a helper function
    # I was passing the TextInput object to the parser instead of the user-entered string, map the input_str to datetime using -> and handle if it is None
    # from the get go
    @staticmethod
    def parse_datetime(input_str: str) -> datetime | None: 
        """Try parsing a date string in multiple formats."""

        formats = [
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M",
            "%Y.%m.%d %H:%M",
            "%Y%m%d %H:%M",
            "%Y-%m-%dT%H:%M",  # ISO
        ]
        for fmt in formats:
            try:

                dt = datetime.strptime(input_str, fmt)
                # Assume user entered UTC if no tz given by the format
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        # Fallback to dateutil
        try:
            dt = parser.parse(input_str)
        except Exception:
            return None

        if dt.tzinfo is None:

            # If there is no tzinfo on parsed result, assume the user meant UTC
            return dt.replace(tzinfo=timezone.utc)
        
        # If it had an explicit timezone, convert it to UTC
        return dt.astimezone(timezone.utc)

    # nested helper function to check the time format string on submit
    async def on_submit(self, interaction: discord.Interaction):

        # try saving the time requested by user using modals to the datatbase and parse reminder time using the static method/helper function
        # USE `.value` to access what the user typed

        date_text = self.date.value.strip()
        message_text = self.message.value.strip()
        dm_text = self.dm.value.strip()

        # store remind_time variable from the parse_datetime method, as the date_text we set earlier
        remind_time = self.parse_datetime(date_text)
        if remind_time is None:
            await interaction.response.send_message(
                "Invalid date format.\nTry `YYYY-MM-DD HH:MM` (UTC) or " 
                "include a timezone (e.g. `2025-10-05 14:30+00:00`).",
                ephemeral=True,
            )
            return
        
        # User can't be trusted, enforce future time and not some arbitrary string that could be in the past
        # optional: enforce future time
        now = datetime.now(timezone.utc)
        if remind_time <= now:
            await interaction.response.send_message("Please choose a time in the future (UTC).",ephemeral=True,)
            return

        # setting the dm preference
        dm_value = dm_text.lower() in ("yes", "true", "1", "y")

        # Check existing reminders, use list iteration for the user id in insertion schema which is r[1] index
        today = datetime.now(timezone.utc).date()
        existing_today = [
            r for r in get_reminders()
            if r[1] == interaction.user.id and parser.isoparse(r[4]).date() == today
        ]
        if existing_today:
            await interaction.response.send_message("You already have an active reminder today.", ephemeral=True)
            return

        # store timezone-aware datetime, only convert to string here if DB expects it (which it doesnt really atm), then get the ID of the reminder
        # we have just inserted 
        reminder_id = add_reminder(
            interaction.user.id,
            interaction.channel.id,
            message_text,
            remind_time,
            dm_value
        )

        # schedule the reminder
        # use the tracked scheduler instead of create_task directly
        schedule_reminder(
            reminder_id,
            interaction.user.id,
            interaction.channel.id,
            message_text,
            remind_time,
            dm_value
        )

        # send confirmation message to user
        await interaction.response.send_message(
            f"✅ Reminder set for {remind_time.strftime('%Y-%m-%d %H:%M UTC')}",
            ephemeral=True
        )



@bot.tree.command(name="remindme", description="Set a reminder (once per day).")
async def remindme(interaction: discord.Interaction):
    """ Open the reminder creation modal. """

    await interaction.response.send_modal(ReminderModal())



# TODO maybe not just delete the whole task directly from db, but read asyncio's docs to remove/delete the reminder itself. Probably will save a bit
# of memory too
@bot.tree.command(name="myreminders", description="List or cancel your reminders.")
async def myreminders(interaction: Interaction):
    """ command to list the user's reminders and cancel them before they go off, to make a new one """

    # Cancel a reminder, if the cancel id we set matches the id that we saved in the delete_reminder function in utils.py
    reminders = get_user_reminders(interaction.user.id)
    if not reminders:
        await interaction.response.send_message("You have no active reminders.", ephemeral=True)
        return

    # Build a Select dropdown for reminders, store options as a list parse the time set by user as an ISO in the correct string format
    options = []
    for r in reminders:
        reminder_id, _, _, message, time_str, dm_flag = r
        time_fmt = parser.isoparse(time_str).strftime("%Y-%m-%d %H:%M UTC")
        label = f"{message[:50]} ({time_fmt})"
        description = "DM" if dm_flag else "Channel"
        options.append(discord.SelectOption(label=label, description=description, value=str(reminder_id)))

    select = Select(
        placeholder="Choose a reminder to cancel...",
        options=options,
        min_values=1,
        max_values=1,
    )

    # NOTE this is deprecated because i dont want to use /myreminders cancel_id:<id> as its messy for the user
    """ if cancel_id is not None:
            delete_reminder(cancel_id)
            await interaction.response.send_message(f"Reminder {cancel_id} canceled.", ephemeral=True)
            return
    """

    # helper function for quick call to delete a reminder within the myreminder command itself 
    async def select_callback(interaction2: Interaction):

        reminder_id = int(select.values[0])

        # make sure ther eis afallbakc, if no issues or if indeed issues, let the user know.
        success = delete_reminder(reminder_id, interaction2.user.id)
        if success:
             # Cancel the running asyncio task
            task = scheduled_reminders.pop(reminder_id, None)
            if task:
                task.cancel()

            await interaction2.response.edit_message(
                content=f"Reminder {reminder_id} canceled.",
                view=None
            )
        else:
            await interaction2.response.edit_message(
                content="Could not cancel that reminder — it may already have been deleted.",
                view=None
            )

    select.callback = select_callback

    view = View()
    view.add_item(select)

    await interaction.response.send_message("Here are your active reminders. Select it to cancel:",view=view,ephemeral=True)



# This will print embed descriptions so we can see exactly what text is there (for reverse engineering websocket requests of other bots)
@bot.tree.command(name="show_apollo_embeds", description="Show Apollo embed descriptions.")
@app_commands.describe(limit="Number of messages to scan (default 50)")
async def show_apollo_embeds(interaction: discord.Interaction, limit: int = 50):

    """ 
    This command allows you to do the first 'reverse engineering' part ie, shows ALL aspects of an apollo embed for an event or anything else,
        that the bot has 'posted' in any channel. 
        - Can be adapted for any bot or embed, just change this `if "Apollo" in msg.author.name:` bit, from 'Apollo' to whichever user or bot you want.
    """

    required_role = discord.utils.get(interaction.user.roles, name="NCO")
    if required_role is None:
        await interaction.response.send_message("You must be an **NCO** to use this command.", ephemeral=True)
        return

    found = 0
    limit = min(limit, 200)

    async for msg in interaction.channel.history(limit=limit):
        if "Apollo" in msg.author.name:
            found += 1
            for embed in msg.embeds:
                await interaction.channel.send(f"Embed description:\n```{embed.description}```")

    if found == 0:
        await interaction.response.send_message(f"No Apollo messages found in last {limit} messages.")
    else:
        await interaction.response.send_message(f"Found {found} Apollo messages.", ephemeral=True)


# lets list recent messages and their authors
@bot.tree.command(name="recent_authors", description="Show recent authors from the channel.")
@app_commands.describe(limit="Number of messages to scan (default 20)")
async def recent_authors(interaction: discord.Interaction, limit: int = 20):

    """ Command that lets you scan the members/users who have made message/post in the desired channel, and show you who they are."""

    required_role = discord.utils.get(interaction.user.roles, name="NCO")
    if required_role is None:
        await interaction.response.send_message("You must be an **NCO** to use this command.", ephemeral=True)
        return

    authors = set()
    limit = min(limit, 200)

    async for msg in interaction.channel.history(limit=limit):
        authors.add(msg.author.name)

    result = ", ".join(authors)
    await interaction.response.send_message(
        f"Recent authors from last {limit} messages:\n{result}"
    )



@bot.tree.command(name="clear_cache", description="Clears all cached event attendance data scanned from Apollo to re-run data sensitive commands.")
async def clear_cache(interaction: discord.Interaction):

    """ Clears the bots logs and cache to re run data sensitive commands """

    required_role = discord.utils.get(interaction.user.roles, name="NCO")
    if required_role is None:
        await interaction.response.send_message("You must be an **NCO** to use this command.", ephemeral=True)
        return

    # Clear global logs defined globally
    event_log.clear()

    # clear attention log as well
    if 'attendance_log' in globals():
        attendance_log.clear()

    await interaction.response.send_message("Apollo scan cache cleared successfully.", ephemeral=True)


@bot.tree.command(name="hilf", description="Show all available commands and their usage.")
async def hilf(interaction: discord.Interaction):

    """ Help command to see all available commands, as embeds to stay within message limits. """

    await interaction.response.defer()  # defer in case it takes a moment

    embed = discord.Embed(
        title="Attendance Bot Commands",
        description="This bot tracks Apollo event reactions to summarize user participation. More commands to be added.",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="/scan_apollo",
        value="Scans recent Apollo messages and logs users who reacted with ✅ or :accepted: and who reacted with ❌ or :declined:.",
        inline=False
    )

    embed.add_field(
        name="/leaderboard",
        value="Shows this month's attendance leaderboard, based on unique events attended.",
        inline=False
    )

    embed.add_field(
        name="/show_apollo_embeds",
        value="Prints the descriptions of recent Apollo embeds for \"debugging\". This is the actual command that exposes the embeds and other formats of the Apollo bot to \"reverse engineer\" whatever the bot embeds in order to make your own version thereof.",
        inline=False
    )

    embed.add_field(
        name="/remindme",
        value="Allows you to set a reminder in iso format for UTC. So like this 2025-10-01 05:00 then choose your UTC difference, +2 or +6 etc. The bot will then send you a dm with the reminder. Users are limit to one reminder per day per user, unless you cancel the existing reminder and make a new one."
    )

    embed.add_field(
        name="/myreminders",
        value="Allows you to check your active reminder and keep track of it or delete the reminder."
    )

    embed.add_field(
        name="/recent_authors",
        value="Lists authors of the last 'n' messages in the channel. Mainly used for debugging or simply finding out who has made messages. This command is used to figure out if it was apollo bot, or another bot/author that made the message/post.",
        inline=False
    )

    embed.add_field(
        name="/scan_all_reactions",
        value="Mainly used for analysing the reactions to messages, includes all reaction types and which member reacted with what.",
        inline=False
    )

    embed.add_field(
        name="/debug_duplicates",
        value="If you get duplicate reactions, you check how many and which of those were duplicate and why, since this will be a common issue, especially for escape sequences and non standard usernames.",
        inline=False
    )

    embed.add_field(
        name="/staff_meeting_notes",
        value="Paste staff meeting notes markdown text template.",
        inline=False
    )

    embed.add_field(
        name="/summary",
        value="Shows an attendance summary comparing reactions vs non-reactions to determine activity of members.",
        inline=False
    )

    embed.add_field(
        name="/check_member",
        value="Shows activity summary about a selected member for upto 3 past months (24 events, 3 * 8 bot posts).",
        inline=False
    )

    embed.add_field(
        name="/flip",
        value="Flip a coin n number of times. Default 1.",
        inline=False
    )

    embed.add_field(
        name="/rand",
        value="Generate a random number between 0 and 1,000,000 (max n numbers 100).",
        inline=False
    )

    embed.add_field(
        name="/clear_cache",
        value="Clears all cache to re-run and avoid duplicate data collection for data sensitive commands like \"scan_apollo\".",
        inline=False
    )

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="staff_meeting_notes", description="Paste staff meeting note template.")
async def staff_meeting_notes(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)  # defer in case it takes a moment

    """ Command takes a markdown file and generates it in the desired/mentioned discord channel. Directly invoked in dockerfile."""

    required_role = discord.utils.get(interaction.user.roles, name="NCO")
    if required_role is None:
        await interaction.response.send_message("You must be an **NCO** to use this command.", ephemeral=True)
        return

    try:
        with open('staff_meeting_note.md', 'r', encoding='utf-8') as file:
            notes_text = file.read()

        if not notes_text.strip():
            await interaction.followup.send("Error: Template file is empty!")
            return

        await interaction.followup.send(notes_text)

    except FileNotFoundError:
        await interaction.followup.send("Error: Template file 'staff_meeting_note.md' not found!")
    except PermissionError:
        await interaction.followup.send("Error: No permission to read the template file!")
    except UnicodeDecodeError:
        await interaction.followup.send("Error: Unable to read template file - encoding issue!")
    except Exception as e:
        await interaction.followup.send(f"Error: An unexpected error occurred: {str(e)}")


@bot.tree.command(name="debug_apollo", description="Scan recent messages for Apollo embeds and show raw fields for debugging.")
@app_commands.describe(limit="How many recent messages to scan (default 50)")
async def debug_apollo(interaction: discord.Interaction, limit: int = 50):

    """ Debugging function that shows any Apollo message and embed if found. """

    required_role = discord.utils.get(interaction.user.roles, name="NCO")
    if required_role is None:
        await interaction.response.send_message("You must be an **NCO** to use this command.", ephemeral=True)
        return

    await interaction.response.defer()
    found = False
    messages = []

    async for msg in interaction.channel.history(limit=limit):

        if "apollo" in msg.author.name.lower():
            found = True

            if not msg.embeds:
                messages.append("Apollo message found, but has no embeds.")
                continue

            for embed in msg.embeds:
                title = embed.title or "No Title"
                description = embed.description or "No Description"
                messages.append(f"**Embed Title:** {title}\n```{description}```")

                for field in embed.fields:
                    name = field.name or "Unnamed Field"
                    value = field.value or "No Value"
                    chunk = f"**{name}**:\n```{value}```"
                    messages.append(chunk)

    if not found:
        await interaction.followup.send("No Apollo messages found in recent history.")
        return

    if not messages:
        await interaction.followup.send("Apollo messages found, but no embeds to show.")
        return

    # Send messages in chunks under 1900 characters
    chunk = ""
    for msg in messages:
        if len(chunk) + len(msg) > 1900:
            await interaction.followup.send(chunk)
            chunk = ""
        chunk += msg + "\n\n"

    if chunk:
        await interaction.followup.send(chunk)


@bot.tree.command(name="debug_duplicates", description="Check for inconsistent (duplicate-looking) usernames in attendance log.")
async def debug_duplicates(interaction: discord.Interaction):

    """ 
    Checks global dict 'attendance_log' by readding them into a tmep dict 'seen' to prevent users being accounted for 2x.
        - This is due to the messy nature of the function and how it interacts with the 'normalize_name' function.
        - The normalized names are passed to the temp list (by called the normalized_name function) and outputs a message in discord accordingly.
    """

    required_role = discord.utils.get(interaction.user.roles, name="NCO")
    if required_role is None:
        await interaction.response.send_message("You must be an **NCO** to use this command.", ephemeral=True)
        return

    seen = defaultdict(set)

    # Normalize usernames and group them
    for entry in attendance_log.values():
        normalized = normalize_name(entry["username"])
        seen[normalized].add(entry["username"])

    duplicates = {k: v for k, v in seen.items() if len(v) > 1}

    # Defer in case it takes time
    await interaction.response.defer(thingking=True)

    if not duplicates:
        await interaction.followup.send("No username inconsistencies found.")
    else:
        lines = ["Inconsistent usernames found:"]
        for k, versions in duplicates.items():
            lines.append(f"{k}: {', '.join(versions)}")
        
        message = "\n".join(lines)
        if len(message) > 1900:
            for chunk in [message[i:i+1900] for i in range(0, len(message), 1900)]:
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(message)


@bot.tree.command(name="scan_apollo", description="Scan Apollo event embeds and log attendance.")
@app_commands.describe(limit="Number of messages to scan (default 18, max 100)")
async def scan_apollo(interaction: discord.Interaction, limit: int = 18):

    """ 
    The bot command that calls the 'scan_apollo_events' function to scan apollo-bot embeds and output the reactions and/or
        reactions thereto.
    """
    
    required_role = discord.utils.get(interaction.user.roles, name="NCO")
    if required_role is None:
        await interaction.response.send_message("You must be an **NCO** to use this command.", ephemeral=True)
        return


    await interaction.response.defer(thinking=True)

    scanned, logged = await scan_apollo_events(limit)
    await interaction.followup.send(
    f"Scanned {scanned} messages, found {len(event_log)} Apollo events, logged {logged} attendees (target: {limit} events)."
)


# -----  NOTE  ----- 
    # This has been "commented out" as it is legacy now (v1.0) This command didnt call the 'scan_apollo_events' function but instead,
    # did everything in one bot command. I mainly did it for prototyping the "reverse engineering" bit and its kinda useful if you want to have
    # a lightweight embed extraction function built directly into a bot command, and not use it anywhere else
"""
@bot.tree.command(name="scan_apollo", description="Scan Apollo event embeds and log attendance.")
@app_commands.describe(limit="Number of messages to scan (default 18, max 100)")
async def scan_apollo(interaction: discord.Interaction, limit: int = 18):

    required_role = discord.utils.get(interaction.user.roles, name="NCO")
    if required_role is None:
        await interaction.response.send_message("You must be an **NCO** to use this command.", ephemeral=True)
        return

    # initialise scanned and logged as 0
    scanned = 0
    logged = 0

    # limit the apollo scans to a max of 100
    limit = min(limit, 100)

    # Ensure CHANNEL_ID is int or convert
    # also, if you dont want to hard-code the channel id and instead want to type the channel id as an argument to the command, you can do so
    target_channel = bot.get_channel(int(CHANNEL_ID))
    if not target_channel:
        await interaction.response.send_message("Failed to fetch the announcements channel.")
        return

    # the thining is "the bot is thinking", which is set to true
    await interaction.response.defer(thinking=True)

    # NOTE -> here on, we will be focusing on scanning the actual apollo messages

    # for every message in the target channel, with the current limit of how many prior messages to scan, we will check if its a message by apollo first
    async for msg in target_channel.history(limit=limit):
        if "Apollo" not in msg.author.name:
            continue
        
        # if it is apollo, increment scanned messages count by 1
        scanned += 1

        # ---- NOTE ----
        # the way Apollo does its ✅, ❌ for example is not the actual emoji, that would be :white_check_mark: and :x: . Rather apollo has its own
        # server side embeds which it displays as those emojis in its default functionality, for attendance of the event as:
        # :accepted: :declined:

        # NOTE: The "embed" object here, refers to an instance of discord.Embed, which is a class provided by the discord.py library representing 
        # a rich content "embed" attached to a Discord message. 
        # Discord allows bots and users to send rich messages containing fields, colors, thumbnails, and descriptions

         
        A typical Apollo embed could be like:
                embed.title: "Training Operation - June 17"

                embed.description: "- Cpl C. Hart\n- Pvt M. Doe"

                embed.fields:

                Field 1: Name = "Accepted ✅", Value = "- PFC Jane\n- LCpl Bob"

                Field 2: Name = "Declined ❌", Value = "- Pvt Ray" 
        

        # then for each embed in the the message embeds, set a list of what embed we want to keep track of ie: here we keep track of attendees and declined
        # but that goes for literally anything else, using any other of apollo's function, thats why the "/show_apollo_embeds" function exists
        # So we are looping through all embed objects attached to a single message 'msg'
        for embed in msg.embeds:
            attendees = []
            declined = []

            # then fo each field in the embeds' fields, check for both accepted and declined
            # embed.fields is a list of named fields in that embed (e.g., "Accepted", "Declined").
            for field in embed.fields:

                # strip them of their standard apollo format, and appent the plain names to the attendees dict, do the same for declined
                # parse the .value of each field to extract user names by "normalising" them
                if "accepted" in field.name.lower():
                    for line in field.value.split("\n"):
                        name = line.strip("- ").strip()
                        if name:
                            attendees.append(name)

                if "declined" in field.name.lower() or "x" in field.name.lower():
                    for line in field.value.split("\n"):
                        name = line.strip("- ").strip()
                        if name:
                            declined.append(name)

            # the embed object description, is how the bot parses each description for each line in the description of event but remember:
            # this condition is outside the field loop, but inside the main msg embed loop so the description embed is here, for this specific use case,
            # showing the 
            if embed.description:
                for line in embed.description.split("\n"):
                    if line.strip().startswith("-"):
                        name = line.strip("- ").strip()
                        if name:
                            attendees.append(name)

            # debug loop for seeing the exact inner workings of the bot embeds in json like format
            for embed in msg.embeds:
                print(embed.to_dict())

            # we then want to get tuples of the names in each of the 2 lists we have so far, and call the normalized_name function on it, 
            # to well... normalize them using list iteration
            normalized_declined = [(normalize_name(name), name) for name in declined]
            normalized_attendees = [(normalize_name(name), name) for name in attendees]

            # append the MAIN list, at global level which is keeping track of mapping the attributes to the id's like we see below
            event_log.append({
                "event_id": msg.id,
                "accepted": normalized_attendees,
                "declined": normalized_declined
            })

            # now im "pretty printing" it so i dont want to see ".username_x" but their actual server name like in a milsim server (Pvt M. Cooper)
            # for every user_id and pretty name in each of the lists ie, "attendees" and "declined", we first want to check if they are already logged
            # by calling the "already_logged" function with the "pseudo_id" to prevent duplicates, and if thats not the casem we append logged by 1
            for user_id, pretty in normalized_attendees:
                pseudo_id = f"{msg.id}-{user_id}"
                if not already_logged(pseudo_id):
                    log_attendance(user_id, pretty, msg.id)
                    logged += 1

            # fore declined we do the same, but we pass the response parameter and check for all declined users
            for user_id, pretty in normalized_declined:
                pseudo_id = f"{msg.id}-{user_id}-declined"
                if not already_logged(pseudo_id):
                    log_attendance(user_id, pretty, msg.id, response="declined")
                    logged += 1

    await interaction.followup.send(
        f"Scanned {scanned} Apollo events, logged {logged} attendees (limit: {limit})."
    )
"""

@bot.tree.command(name="check_member", description="Show attendance data about a single member.")
@app_commands.describe(user="The member to check", limit="Limit of how many events to check for. (default 8, max 24)")
async def check_member(interaction: discord.Interaction, user: discord.Member, limit: app_commands.Range[int, 1, 24] = 8):

    """ Function allows to check an active members's 'stats' and filter by name/squad/rank """

    required_role = discord.utils.get(interaction.user.roles, name="NCO")
    if required_role is None:
        await interaction.response.send_message("You must be an **NCO** to use this command.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    # add check to make sure we are above the min limit
    if len(event_log) < limit:
        await interaction.followup.send(f"Only {len(event_log)} events scanned. Use `/scan_apollo` first.")
        return

    # build a list of the last "limit" unique events to reduce duplication
    def event_key(ev):
        # try several common keys, fallback to None
        return ev.get("id") or ev.get("message_id") or ev.get("timestamp") or ev.get("title")

    seen = set()
    unique_events = []

    # iterate from newest to oldest, collect unique keys until we have "limit"
    for ev in reversed(event_log):
        key = event_key(ev)

        # if no key present, we fallback to using a string representation for dedupe
        dedupe_key = key if key is not None else repr(ev)
        if dedupe_key in seen:
            continue
        
        seen.add(dedupe_key)
        unique_events.append(ev)
        if len(unique_events) >= limit:
            break

    recent_events = list(reversed(unique_events))  # restore chronological order

    # normalize the user name like scan_apollo does
    normalized_target = normalize_name(user.display_name)

    accepted = 0
    declined = 0
    no_response = 0

    def extract_uid(entry):
        """Safely extract the 'uid' like value from an accepted/declined entry.
           Accepts tuples/lists like (uid, extra) or plain strings/ints."""
        
        if isinstance(entry, (list, tuple)) and len(entry) > 0:
            return entry[0]
        return entry

    for idx, event in enumerate(recent_events, start=1):
        raw_accepted = event.get("accepted", [])
        raw_declined = event.get("declined", [])

        # Normalize accepted names/ids so first stringify then normalise, 
        # AND CHANGE FROM LIST TO SET BECAUSE PYTHON LISTS DONT HAVE UNIQUE INDEXING
        accepted_names = set()
        for entry in raw_accepted:
            uid = extract_uid(entry)
            try:
                accepted_names.add(normalize_name(str(uid)))
            except Exception:
                logging.exception("Error normalizing accepted entry in event %s: %r", event_key(event) or f"idx{idx}", entry)

        declined_names = set()
        for entry in raw_declined:
            uid = extract_uid(entry)
            try:
                declined_names.add(normalize_name(str(uid)))
            except Exception:
                logging.exception("Error normalizing declined entry in event %s: %r", event_key(event) or f"idx{idx}", entry)

        accepted_match = normalized_target in accepted_names
        declined_match = normalized_target in declined_names

        # log per-event details to help debug why counts are incremented
        logging.debug(
            "check_member: event_idx=%d key=%s raw_accepted=%r accepted_norm=%r accepted_match=%s raw_declined=%r declined_norm=%r declined_match=%s",
            idx,
            event_key(event) or "N/A",
            raw_accepted,
            accepted_names,
            accepted_match,
            raw_declined,
            declined_names,
            declined_match
        )

        if accepted_match and not declined_match:
            accepted += 1
        elif declined_match and not accepted_match:
            declined += 1
        elif not (accepted_match or declined_match):
            no_response += 1

    msg = (
        f"**Attendance for {user.display_name}** (Last {len(recent_events)} Events)\n"
        f"Accepted: **{accepted}** ✅\n"
        f"Declined: **{declined}** ❌\n"
        f"No Response: **{no_response}**"
    )

    await interaction.followup.send(msg)


@bot.tree.command(name="rand", description="Generate a random number in a range.")
@app_commands.describe(limit="Set your upper range (1 to 1,000,000)")
async def rand(interaction: discord.Interaction, limit: app_commands.Range[int, 1, 1_000_001] = 100):

    """ Generate a random number between 1 and `limit`. """

    result = secrets.randbelow(limit) + 1
    await interaction.response.send_message(f"**{result}**")


@bot.tree.command(name="coin", description="Flip a coin 'n' times.")
@app_commands.describe(limit="How many flips to do (default is 1)")
async def coin(interaction: discord.Interaction, limit: app_commands.Range[int, 1, 100] = 1):

    """  Command to flip a coin 'n' times. """

    outcomes = [random.choice(["Heads", "Tails"]) for _ in range(limit)]

    if limit == 1:
        response = f"{outcomes[0]}"

    else:
        heads = outcomes.count("Heads")
        tails = outcomes.count("Tails")

        response = (

            f"coin was flipped {limit} times:\n"
            f"**Heads:** {heads}\n"
            f"**Tails:** {tails}"

        )
    
    await interaction.response.send_message(response)


@bot.tree.command(name="summary", description="Generates a summary of attendance and some data.")
@app_commands.describe(limit="How many Apollo events to summarize (min: 8, max: 24)")
async def summary(interaction: discord.Interaction, limit: app_commands.Range[int, 8, 24] = 8):
    
    """Summarizes user attendance for the last N Apollo events."""

    await interaction.response.defer(thinking=True)

    required_role = discord.utils.get(interaction.user.roles, name="NCO")
    if required_role is None:
        await interaction.response.send_message("You must be an **NCO** to use this command.", ephemeral=True)
        return

    # Collect exactly N Apollo events (not just messages)
    scanned_messages, logged = await scan_apollo_events(limit)

    if len(event_log) < limit:
        await interaction.followup.send(
            f"Only {len(event_log)} Apollo events found (scanned {scanned_messages} messages).\n"
            f"Need at least {limit} events for a full summary.",
            ephemeral=True
        )
        return

    guild = interaction.guild
    excluded_roles = {"Guest", "Reserves", "External Unit Rep"}

    valid_members = [
        m for m in guild.members
        if not m.bot and not any(role.name in excluded_roles for role in m.roles)
    ]
    valid_ids = {m.id for m in valid_members}
    id_to_member = {m.id: m for m in valid_members}

    # Build a mapping: normalized display name -> member
    name_map = {normalize_name(m.display_name): m for m in valid_members}

    # Tally responses per user ID using normalized names
    response_count = defaultdict(int)
    recent_events = event_log[-limit:]

    for event in recent_events:
        for category in ("accepted", "declined"):
            for norm_name, _ in event.get(category, []):
                member = name_map.get(norm_name)
                if member:
                    response_count[member.id] += 1

    low_responders = defaultdict(list)

    threshold = limit // 2  # 50% of events (eg, 8 -> 4, 12 -> 6, 24 -> 12)

    for user_id in valid_ids:
        count = response_count.get(user_id, 0)
        if count <= threshold:   # 50% or less
            member = id_to_member.get(user_id)
            if member:
                low_responders[count].append(member)

    lines = [f"**Low Attendance Summary (Last {limit} Apollo Events)**", f"_Showing users with {threshold} or fewer responses (50% or less)_\n"]

    if not low_responders:
        lines.append(f"All active members responded to more than {threshold} events!")
    else:
        for i in range(0, threshold + 1):
            group = low_responders.get(i, [])
            if group:
                lines.append(f"\n**Members with {i}/{limit} Responses:**")
                for member in sorted(group, key=lambda m: m.display_name.lower()):
                    lines.append(f"- **{member.display_name}** ✅❌ | No Response: {limit - i}")

    lines.append(f"\n_Scanned {scanned_messages} messages to find {limit} Apollo events. Logged {logged} participant responses._")

    message = "\n".join(lines)
    if len(message) > 1900:
        for chunk in [message[i:i + 1900] for i in range(0, len(message), 1900)]:
            await interaction.followup.send(chunk)
    else:
        await interaction.followup.send(message)

    # Clear cache after generating summary
    event_log.clear()
    if 'attendance_log' in globals():
        attendance_log.clear()


@bot.tree.command(name="scan_all_reactions", description="Scan recent messages for reactions and summarize them.")
@app_commands.describe(channel="The channel to scan for reactions", limit="How many recent messages to scan (default is 5)")
async def scan_all_reactions(interaction: discord.Interaction, channel: TextChannel, limit: app_commands.Range[int, 1, 100] = 5):

    """ Function uses the TextChannel object from discord's library passed as a parameter, to allow the user to make this command
        in any channel and from any channel, that the bot has message history and other relevant permissions for. """

    required_role = discord.utils.get(interaction.user.roles, name="NCO")
    if required_role is None:
        await interaction.response.send_message("You must be an **NCO** to use this command.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)  # defer in case it takes a moment

    # ensure the bot can read message history in the selected channel
    if not channel.permissions_for(interaction.guild.me).read_message_history:
        await interaction.followup.send(f"Can't read message history in {channel.mention}.")
        return

    # initialise scanned to 0, and a dict of emoji lists
    scanned = 0
    
    # instead of a single emoji_summary, map message -> emoji -> users
    message_summaries = []

    # We want to check every message in the channel this command is made in, and for every message amount mentioned when making the "/command",
    # increment the scanned counter, for the channel provided (dont use 'interaction.channel.history' if you want to preserve channel specificity)
    async for msg in channel.history(limit=limit):
        scanned += 1

        # Skip messages with no reactions
        if not msg.reactions:
            continue

        # Temporary dict of lists of reactions to store reactions for this message
        msg_reactions = defaultdict(list)

        # Only consider users not bots
        for reaction in msg.reactions:
            users = [user async for user in reaction.users()]

            # Only considering users NOT bots, IMP CHECK!
            for user in users:
                if user.bot:
                    continue
                
                # Set a var member, using Discord's guild object and use the get_member method for that user.id, also set display_name to that members
                # display name, if the the user is a member, else just get the discord username (because nickname for non members might not be set)
                member = interaction.guild.get_member(user.id)  
                display_name = member.display_name if member else user.name

                # append the msg_reactions temp dict with the emoji mapped to the display_name
                msg_reactions[str(reaction.emoji)].append(display_name)


        if msg_reactions:

            # Trim message content to first 100 chars for readability
            content_preview = msg.content or "[Embed/Attachment/No Text]"
            content_preview = (content_preview[:100] + "...") if len(content_preview) > 100 else content_preview

            # Now append the message summaries list we made earlier at start of function, with all of the relevant data needed to make sense of the output
            # The data in question is:
                # who wrote the message
                # shortened preview of message
                # link to jump to og message
                # a dict of emoji : list of users who reacted
            message_summaries.append({

            "author": msg.author.display_name,
            "content": content_preview,
            "link": msg.jump_url,
            "reactions": msg_reactions

            })

    # Check for if the messages even exist
    if not message_summaries:
        await interaction.followup.send(f"No reactions found in the last {limit} messages of {channel.mention}.")
        return

    # Set a list of lines as an f string to show number of scanned messages
    lines = [f"**Reactions Summary (from last {scanned} messages in {channel.mention})**\n"]

    # Now we create nested loops, the outer loop appends the message data, that we just appeneded to message/summaries, but here we want to append it to
    # the lines list to sort of concatonate the message data for the summaries list AND the reactions thereof
    for msg_data in message_summaries:
        
        # Append the data to the lines list, and update k:v pairs. Appending twice for better output and more readable, the second appnd is in markdown,
        # for better discord look 
        lines.append(f"**Message by {msg_data['author']}**: {msg_data['content']}\n")
        lines.append(f"> [Jump to message]({msg_data['link']})")

        # Then for each emoji, user in the emoji_summary dict (we are unpacking the dict, using .items() to index into the dict)
        for emoji, users in msg_data['reactions'].items():

            # Get a set of unique users
            unique_users = set(users)

            # Append the 'lines' list with the f string of each emoji, mapped to each set of users
            lines.append(f"> {emoji} - {len(users)} reaction(s) from: {', '.join(unique_users)}")

        # Blank line between messages, if the number of messages to be shown > 1
        lines.append("")

    await interaction.followup.send("\n".join(lines))


# TODO: Add explicit Astro Award and Good Conduct award automatically in the end summary
# The command to show the leaderboard
# for slash commands using @bot.tree.command, the callback function must accept a discord.Interaction as the first argument, not ctx
# wherever using ctx.send(), it should become interaction.response.send_message() or interaction.followup.send() depending on 
# whether we're deferring the response.
@bot.tree.command(name="leaderboard", description="Show a ranked summary leaderboard of accepted and declined for the last 8 events")
async def leaderboard(interaction: discord.Interaction):

    """ 
    Command reads from the global event_log list and attendance_log dict to rank and summarize user attendance based on cached data,
        from using the scan_apollo command.
        - There is no persistent save implementation in attbot.py as I had no need for it, for that you might want to look at botscanner.py.
        - Functionality of this command can be adapted for any other rank based uses, just read the comments and you'll get an idea.
    """

    required_role = discord.utils.get(interaction.user.roles, name="NCO")
    if required_role is None:
        await interaction.response.send_message("You must be an **NCO** to use this command.", ephemeral=True)
        return

    # if the global dict "event_log" is empty, then no messages have been scanned
    if len(event_log) == 0:
        await interaction.response.send_message("No events have been scanned yet.")
        return

    # ser recent events to the event_log dict but only 8 bot messages from Apollo
    recent_events = event_log[-8:]

    # now we want to set a dict for each type of reaction 
    # NOTE--- in this case its only accepted and declined because thats my use case, you can have multiple, just follow this template/general idea

    # the general idea being, we want EACH parsed representation of a type of reaction-user mapping to be its own datastructure for cleanliness and 
    # separation of concerns. I want the number of declined and accepted, a set of unique users and a dict of pretty names (nickname scanned by "scan_apollo")
    accepted_count = defaultdict(int)
    declined_count = defaultdict(int)
    unique_users = set()
    pretty_names = {}

    # for every event in the scanned recent events, we will be going over the accepted reactions and declined reactions
    for event in recent_events:

        # then for each normal user_id and the pretty version thereof in the accepted category list of that event,
        for user_id, pretty in event["accepted"]:

            # increment the accepted count dict by 1, then for every user_id in the pretty_names dict, we set that to the pretty ie, the nickname, and 
            # add that user_id to the set of unique users
            accepted_count[user_id] += 1
            pretty_names[user_id] = pretty
            unique_users.add(user_id)

        # similar for declined users, just that we use event.get, a temp list of declined while iterating, to keep track of how many user_id and pretty
        for user_id, pretty in event.get("declined", []):

            # increment the declined users by 1, add that user_id to the unique users set, and strip any trailing/leading whitespace before setting
            # those user_id equal to the user_id in the pretty_names dict
            declined_count[user_id] += 1
            unique_users.add(user_id)
            pretty_names[user_id] = pretty.strip()

    # now we want to sort the accepted users, bu counting that dict and using a lambda function that sorts them by descending
    accepted_sorted = sorted(
        accepted_count.items(),
        key=lambda x: (-x[1], x[0])
    )

    # we want a similar 'lines' list as previous function to show the leaderboard
    lines = [f"**Attendance Leaderboard {datetime.now().strftime('%B')}**"]
    total_events = len(recent_events)

    # and for each user 'user_id' and the 'count' (tuple) we want to number it firstly, then, append to the lines list by using the fstring of how we want
    # the data to be shown
    for i, (user_id, count) in enumerate(accepted_sorted, start=1):
        lines.append(f"{i}. **{pretty_names[user_id]}** - {count}/{total_events} events ✅")

    # check how many unique attendees if at all
    if accepted_count:
        lines.append(f"\nTotal unique attendees (accepted): {len(accepted_count)}")
    else:
        lines.append("\nNo attendees found in last 8 events.")

    # then we make a declined exclusive dict, where we are using dict iteration to check key-name, for value-count, in the declined_count dict, is only there
    # if its not there in the accepted_count dict. SO, if they declined, they should not be in accepted dict
    declined_only = {
        name: count for name, count in declined_count.items()
        if name not in accepted_count
    }

    # if that above dict is true, append to the lines list with an fstring to show the data, same as accepted_sorted
    if declined_only:

        lines.append(f"\n**Declined (❌)**")
        declined_sorted = sorted(
            declined_only.items(),
            key=lambda x: (-x[1], x[0])
        )

        for i, (norm_name, count) in enumerate(declined_sorted, start=1):

            display_name = pretty_names.get(norm_name, norm_name).strip()
            lines.append(f"{i}. **{display_name}** - {count} declines ❌")

    lines.append(f"\nTotal unique responders: {len(unique_users)}")

    # Astro Award - members who accepted all 8 events
    astro_award_winners = [
        pretty_names[user_id]
        for user_id, count in accepted_count.items()
        if count == total_events
    ]

    if astro_award_winners:
        lines.append("\n**Astro Award**")
        for winner in astro_award_winners:
            lines.append(f"🏅 {winner} - Attended all {total_events} events!")

    # Same for good conduct award - members who reacted to all events (accepted or declined)
    reacted_all_events = [
        pretty_names[user_id]
        for user_id in unique_users
        if accepted_count[user_id] + declined_count[user_id] == total_events
    ]

    if reacted_all_events:
        lines.append("\n**Good Conduct Award**")
        for member in reacted_all_events:
            lines.append(f"🏅 {member} - Reacted to all {total_events} events!")

    # if message exceeds character limit then send the next chunk in a new line/message
    message = "\n".join(lines)

    # defer response to allow time if needed
    await interaction.response.defer(thinking=True)

    # send large messages in chunks
    if len(message) > 1900:
        for chunk in [message[i:i+1900] for i in range(0, len(message), 1900)]:
            await interaction.followup.send(chunk)
    else:
        await interaction.followup.send(message)

# Run the bot with token of server
bot.run(TOKEN)
	
	
	