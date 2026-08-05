import sqlite3

from config import DATABASE_URL


def connect():
    return sqlite3.connect(DATABASE_URL)


def find_account(email):
    # Planted defect: user input concatenated straight into SQL.
    query = "SELECT id, email, balance FROM accounts WHERE email = '" + email + "'"
    with connect() as connection:
        return connection.execute(query).fetchone()


def transfer(from_id, to_id, amount):
    with connect() as connection:
        connection.execute(
            "UPDATE accounts SET balance = balance - ? WHERE id = ?", (amount, from_id)
        )
        connection.execute(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?", (amount, to_id)
        )
