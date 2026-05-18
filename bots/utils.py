# This utils file handles the helper functions for the database and functions of the database itself. 

import sqlite3
import os
import logging
from pathlib import Path
from datetime import datetime, timezone
from dateutil import parser
from typing import Union

# Configurable DB path
# Default location is in the same directory as the script
DEFAULT_DB_NAME = "reminders.db"

# set a defined path to the reminders database
# use os maybe to ensure SQLite always tries to use the same place as the script instead of relying on the working dir?
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.getenv("REMINDERS_DB_PATH", os.path.join(BASE_DIR, DEFAULT_DB_NAME))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

""" Table schema we are using below for insertion and creation of reminders
+--------------------------------------------------------------------+
| Index  | Column        | Type      | Example Value                 |
| ------ | ------------- | --------- | ----------------------------- |
|  r[0]  |  id           | int       |  1                            |
|  r[1]  |  user_id      | int       |  1234567890                   |
|  r[2]  |  channel_id   | int       |  9876543210                   |
|  r[3]  |  message      | str       |  "Staff Meeting"              |
|  r[4]  |  remind_time  | str (ISO) |  "2025-10-04T12:00:00+00:00"  |
|  r[5]  |  dm           | int (0/1) |  1                            |
+--------------------------------------------------------------------+
"""

def init_db(db_path=DB_PATH):
    """ init function to create the reminders database and if it does exist, open the db and read/write from and to it """

    # elaborate logging 
    logging.info(f"Initializing database at: {DB_PATH}")

    # add a set path so maybe i can ensure the path exists?
    logging.info(f"Init DB on {DB_PATH}")

    # make the directory by default
    os.makedirs(os.path.dirname(BASE_DIR), exist_ok=True)

    Path(db_path).touch(exist_ok=True)
    
    # create connection, and create the the reminders table if it doesnt exist already
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            remind_time TEXT NOT NULL,
            dm INTEGER NOT NULL
        )
    """)

    # second table for quotes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            quote TEXT NOT NULL,
            created_at TEXT NOT NULL,
            quoted_user_id INTEGER,
            quoted_username TEXT
        )
    """)
    conn.commit()
    conn.close()
    logging.info(f"Init DB successfull on {DB_PATH}")



def get_user_reminders(user_id: int, db_path=DB_PATH):
    """ Give user the option to cancel a reminder if they put one accidentally or made a mistake. """

    # create a connection to dbase, select all reminders of the user who made the command NOTE this funtion is tied to the "myreminder" command in attbot.py
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(""" SELECT id, user_id, channel_id, message, remind_time, dm FROM reminders WHERE user_id = ? """, (user_id,))

    rows = cursor.fetchall()
    conn.close()
    return rows 



# Command for adding a reminder, takes input of user id, channel id, the message to save as a string, time to be reminded as, as a string as well and the
# dm to send to the user. 
# Also using "Union" for type safety and because we call ".astimezone" so if its a string, we dont get an AttributeError at runtime.
def add_reminder(user_id: int, channel_id: int, message: str, remind_time: Union[str, datetime], dm: bool, db_path=DB_PATH):

    """ remind_time may be a datetime or an ISO string. This function normalizes the time to
    a UTC-aware ISO string before inserting into the DB. """

    # try to parse string times into datetime if needed, or fallback on ISO times
    if isinstance(remind_time, str):
        try:
            remind_time = parser.isoparse(remind_time)
        except Exception:
            # fallback to fromisoformat for slightly different inputs
            remind_time = datetime.fromisoformat(remind_time)

    # ensure we now have a datetime
    if not isinstance(remind_time, datetime):
        raise TypeError("remind_time must be a datetime or ISO-formatted string")

    # hard coding the remind_time in ISO format, .astimezone is a datetime method 
    remind_time_utc = remind_time.astimezone(timezone.utc)
    remind_time_str = remind_time_utc.isoformat()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO reminders (user_id, channel_id, message, remind_time, dm) VALUES (?, ?, ?, ?, ?)"""
                   ,(user_id, channel_id, message, remind_time_str, int(dm)))
    
    reminder_id = cursor.lastrowid
    
    # commit the insertion and close connection
    conn.commit()
    conn.close()

    return reminder_id



# function to get reminders for the user, to see what and how many reminders they have
def get_reminders(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, channel_id, message, remind_time, dm FROM reminders")
    rows = cursor.fetchall()
    conn.close()
    return rows



# functionality delete a reminder if a user wishes to
def delete_reminder(reminder_id: int, user_id: int, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # make sure one user cant delete another user's reminders 
    cursor.execute(
        "DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0


def migrate_add_quoted_user(db_path=DB_PATH):

    """Run once to add quoted_user columns if they don't exist yet."""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE quotes ADD COLUMN quoted_user_id INTEGER")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        cursor.execute("ALTER TABLE quotes ADD COLUMN quoted_username TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

# TODO add a quote function to let users add a quote, request a random quote, and pass an argument to request a quote from a specific person
def add_quote(user_id: int, username: str, quote: str,
              quoted_user_id: int, quoted_username: str,   # NEW
              db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    created_at = datetime.now(timezone.utc).isoformat()
    cursor.execute(
        """INSERT INTO quotes
           (user_id, username, quote, created_at, quoted_user_id, quoted_username)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, username, quote, created_at, quoted_user_id, quoted_username)
    )
    quote_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return quote_id


def delete_quote(user_id: int, quote_id: int, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM quotes WHERE id = ? AND user_id = ?", (quote_id, user_id))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted > 0


def get_random_quote(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, user_id, username, quote, created_at, quoted_username
           FROM quotes ORDER BY RANDOM() LIMIT 1"""
    )
    row = cursor.fetchone()
    conn.close()
    return row


def get_random_quote_by_user(quoted_user_id: int, db_path=DB_PATH):
    """Now filters by WHO SAID the quote, not who added it."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, user_id, username, quote, created_at, quoted_username
           FROM quotes
           WHERE quoted_user_id = ?
           ORDER BY RANDOM() LIMIT 1""",
        (quoted_user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    return row  # None if user has no quotes


def get_user_quotes(user_id: int, db_path=DB_PATH):

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT id, user_id, username, quote, created_at, quoted_username FROM quotes WHERE user_id = ?",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows

