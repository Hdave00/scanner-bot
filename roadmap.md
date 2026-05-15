# Bot Roadmap

## Overview

This bot currently reverse engineers Apollo's premium embed features to handle member attendance tracking. The goal of this roadmap is to phase out Apollo and all other third-party bot dependencies entirely, replacing them with native functionality built directly into this bot.

The motivation for this is threefold: increasing restrictions on third-party Discord APIs, paywalled bot features, and Discord's own uncertain future regarding privacy policy and government ID requirements.

---

## Current State

The bot depends on Apollo embeds to power two commands:

- `leaderboard` - ranks members by attendance across recent events
- `summary` - flags members with low response rates across recent events

Both commands parse Apollo embed fields and resolve Discord members by name. The scan and resolution logic is handled by `scan_apollo_events()`.

---

## Phase 1 - Native Event System

Replace Apollo's event posting with a native event embed, built and managed by this bot.

### Event Embed Structure

Each event embed must include the following fields:

| Field | Description |
|---|---|
| Title | Name of the event |
| Description | Free-text body |
| Time | Discord timestamp using the universal timestamp format `<t:UNIX:F>` |
| Centurion - Accepted | List of accepted members from Centurion squad |
| Centurion - Declined | List of declined members from Centurion squad |
| Fox Red - Accepted | List of accepted members from Fox Red squad |
| Fox Red - Declined | List of declined members from Fox Red squad |
| Total Signups | Aggregate count of accepted and declined across both squads |
| Created By | The Discord user who created the event |

### Discord universal format specifier/suffix

**R: Relative, says "two weeks ago", or "in 5 years"**

**D: Date, says "July 4, 2021"**

**T: Time, "11:28:27 AM"**

**t: Short Time, "11:28 AM"**

**F: Full, "Monday, July 4, 2021 11:28:27 AM"**

### Reaction System

Reactions are divided by squad. Each squad has two options:

```
Centurion
  [Yes Emoji]  Attending
  [No Emoji]   Not Attending

Fox Red
  [Yes Emoji]  Attending
  [No Emoji]   Not Attending
```

The bot listens for reaction add/remove events and updates the relevant embed field in real time.

### Event Creation Command

A slash command (e.g. `/create-event`) must open a modal or selection flow with editable fields for all embed fields listed above. Every event created this way is independently customisable.

---

## Phase 2 - Automated Monday Announcements

Every Monday at 18:00 GMT, the bot automatically posts two event embeds in order, with a 10-second gap between them.

### Post 1 - Thursday Platoon Training

```
Title:       Thursday's Platoon Training
Time:        Thursday [current week], 18:00 GMT
@everyone:   Yes (default)
Reactions:   Open (default)
```

### Post 2 - Saturday Operation

```
Title:       Saturday's Operation
Time:        Saturday [current week], 18:00 GMT
@everyone:   Yes (default)
Reactions:   Open (default)
```

Both posts must `@everyone` by default. Both posts must follow the full event embed structure defined in Phase 1. The reactions must be ordered by the time the user reacted so if `Cpl J. Banjo` reacted before `MSPC/6 E. Cor` the attendance embed must show in real time the earlier response of `Cpl J. Banjo`

### Scheduler Logic

```python
# Pseudo-logic for the Monday scheduler
# Runs every Monday at 18:00 GMT

async def monday_announcement():
    await post_event(thursday_event)
    await asyncio.sleep(10)
    await post_event(saturday_event)
```

---

## Phase 3 - Reaction Locking

All events, including the two automated Monday posts, must support the ability to close reactions before the event starts.

### Behaviour

- By default, reactions are open indefinitely
- A closing time can be set per event at creation time or edited after the fact
- Once the reaction window closes, the bot removes the reaction components or ignores new reactions and posts a notice in the embed or thread

### Command

```
/close-reactions [event_id] [time]
```

---

## Phase 4 - Pre-Event Reminder Thread

15 minutes before each event starts, the bot must:

1. Create a thread in the event channel
2. Name the thread after the event title and date, e.g. `Thursday's Operation - May 14`
3. Post an embed inside the thread containing:
   - `REMINDER: Event starting in X minutes`
   - A clean link to the original event message
4. Ping every member who reacted accepted (from either squad) in that thread

### Thread Naming Format

```
{Event Title} - {Month} {Day}

Example: Thursday's Operation - May 14
```

### Reminder Embed Structure

```
REMINDER: Event starting in 15 minutes

[Jump to Event](https://discord.com/channels/...)

Attending:
@Cpl J. Banjo @A. Voyd @Cpl M. Mooses ...
```

---

## Notes

- All automated post times are in GMT and must account for BST where applicable
- Discord universal timestamps (`<t:UNIX:R>`) should be used wherever time is displayed so members see it converted to their local timezone automatically
- The leaderboard and summary commands must be updated in a later phase to read from the native event log rather than Apollo embeds