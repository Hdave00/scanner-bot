# This utils file handles the helper functions for the database and functions of the database itself. 

import sqlite3

# Add reminder command, 
def add_reminder(user_id: int, channel_id: int, message: str, remind_time: str, dm: bool):
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reminders (user_id, channel_id, message, remind_time, dm)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, channel_id, message, remind_time, int(dm)))
    conn.commit()
    conn.close()

def get_reminders():
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, channel_id, message, remind_time, dm FROM reminders")
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_reminder(reminder_id: int):
    conn = sqlite3.connect("reminders.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()