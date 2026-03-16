import sqlite3

conn = sqlite3.connect("exchange.db")
cursor = conn.cursor()

cursor.execute("PRAGMA foreign_keys = OFF")
cursor.execute("DELETE FROM trades")
cursor.execute("DELETE FROM orders")
cursor.execute("DELETE FROM wallets")
cursor.execute("DELETE FROM users")
cursor.execute("PRAGMA foreign_keys = ON")

conn.commit()
conn.close()
print("All tables cleared.")