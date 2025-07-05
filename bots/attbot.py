""" 
This is a unique discord bot that reverse-engineers the closed source event and server management bots using the Discord API, essentially forming a
    closed ecosystem extraction. It scans the activity of other bots in the server by creating a websocket with the hosts, using Discord's Gateway API.
"""


import discord
import os
from dotenv import load_dotenv
from datetime import datetime
from discord.ext import commands
from discord import TextChannel
from discord import app_commands
from collections import defaultdict
import re
import random
import secrets


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

@bot.event
async def on_ready():

    print(f"Bot is connected as {bot.user}")
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s).")

    except Exception as e:
        print(f"Error syncing commands: {e}")

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
    await ctx.send(f"Current entries: {len(attendance_log)}")


# This will print embed descriptions so we can see exactly what text is there (for reverse engineering websocket requests of other bots)
@bot.tree.command(name="show_apollo_embeds", description="Show Apollo embed descriptions.")
@app_commands.describe(limit="Number of messages to scan (default 50)")
async def show_apollo_embeds(interaction: discord.Interaction, limit: int = 50):

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
    await interaction.response.defer()

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
    
    required_role = discord.utils.get(interaction.user.roles, name="NCO")
    if required_role is None:
        await interaction.response.send_message("You must be an **NCO** to use this command.", ephemeral=True)
        return

    await interaction.response.defer(thinking=True)

    scanned, logged = await scan_apollo_events(limit)
    await interaction.followup.send(
    f"Scanned {scanned} messages, found {len(event_log)} Apollo events, logged {logged} attendees (target: {limit} events)."
)


"""
# command to gather Apollo data, cause its fucking CLOSED SOURCE!!
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

    # normalize the user name like scan_apollo does
    normalized_target = normalize_name(user.display_name)

    recent_events = event_log[-limit:]
    accepted = 0
    declined = 0

    for event in recent_events:
        accepted_names = [uid for uid, _ in event.get("accepted", [])]
        declined_names = [uid for uid, _ in event.get("declined", [])]

        if normalized_target in accepted_names:
            accepted += 1
        elif normalized_target in declined_names:
            declined += 1

    no_response = limit - (accepted + declined)

    msg = (
        f"**Attendance for {user.display_name}** (Last {limit} Events)\n"
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
    excluded_roles = {"Guest", "Reserves"}

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

    for user_id in valid_ids:
        count = response_count.get(user_id, 0)
        if count < 4:
            member = id_to_member.get(user_id)
            if member:
                low_responders[count].append(member)

    lines = [f"**Low Attendance Summary (Last {limit} Apollo Events)**", "_Showing users with fewer than 4 responses (✅ or ❌)_\n"]

    if not low_responders:
        lines.append("All active members responded to 4 or more events!")
    else:
        for i in range(0, 4):
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
	
	
	