# This utils file handles the helper functions for the database and functions of the database itself. 

import sqlite3
import os
import logging


# set a defined path to the reminders database
# use os maybe to ensure SQLite always tries to use the same place as the script instead of relying on the working dir?
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "reminders.db")

# quick logging info
logging.info(f"DB_PATH = {DB_PATH}")
logging.info(f"DB directory exists? {os.path.exists(os.path.dirname(DB_PATH))}")
logging.info(f"DB directory writable? {os.access(os.path.dirname(DB_PATH), os.W_OK)}")

def init_db():
    """ init function to create the reminders database and if it does exist, open the db and read/write from and to it """

    # elaborate logging 
    logging.info(f"Initializing database at: {DB_PATH}")

    # add a set path so maybe i can ensure the path exists?
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    try:
        conn = sqlite3.connect(DB_PATH)
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
        conn.commit()
        logging.info("Reminders table ensured in database.")
    except sqlite3.Error as e:
        logging.error(f"Error initializing database: {e}")
    finally:
        conn.close()



def get_user_reminders(user_id: int):
    """ Give user the option to cancel a reminder if they put one accidentally or made a mistake. """

    # create a connection to dbase, select all reminders of the user who made the command NOTE this funtion is tied to the "myreminder" command in attbot.py
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute(""" SELECT id, message, remind_time, dm FROM reminders WHERE user_id = ? """, (user_id,))

    rows = cursor.fetchall()
    conn.close()
    return rows 



# Command for adding a reminder, takes input of user it, channel id, the message to save as a string, time to be reminded as, as a string as well and the
# dm to send to the user 
def add_reminder(user_id: int, channel_id: int, message: str, remind_time: str, dm: bool):
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("""INSERT INTO reminders (user_id, channel_id, message, remind_time, dm) VALUES (?, ?, ?, ?, ?)"""
                   ,(user_id, channel_id, message, remind_time, int(dm)))
    
    # commit the insertion and close connection
    conn.commit()
    conn.close()



# function to get reminders for the user, to see what and how many reminders they have
def get_reminders():
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, channel_id, message, remind_time, dm FROM reminders")
    rows = cursor.fetchall()
    conn.close()
    return rows



# functionality delete a reminder if a user wishes to
def delete_reminder(reminder_id: int):
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()