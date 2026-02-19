import sqlite3

# Connect to database (creates it if not exists)
conn = sqlite3.connect("exchange.db")
cursor = conn.cursor()

# Read and execute schema
with open("schema.sql", "r") as f:
    schema = f.read()
    cursor.executescript(schema)

conn.commit()
conn.close()

print(":white_check_mark: Schema applied successfully!")