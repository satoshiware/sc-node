import sqlite3

try:
    # Connect to exchange.db (same folder)
    conn = sqlite3.connect("exchange.db")
    cursor = conn.cursor()

    # Delete all data from both tables
    cursor.execute("DELETE FROM orders;")
    cursor.execute("DELETE FROM trades;")

    conn.commit()
    print("All data deleted from orders and trades tables successfully!")

except Exception as e:
    print("Error:", e)

finally:
    conn.close()
