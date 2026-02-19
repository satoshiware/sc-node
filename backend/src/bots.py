# src/sim_bots.py
import threading
import random
import time
import signal
import sys
from orders import place_order

running = True

def stop(signum, frame):
    global running
    running = False

signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)

def bot(name,work):
    while running:
        side = work
        order_type = random.choices(["limit", "market"], weights=[0.8, 0.2])[0]
        price = None
        if order_type == "limit":
            mid = 100.0
            price = round(mid + random.uniform(-2.0, 2.0), 2)
        quantity = round(random.uniform(0.5, 3.0), 4)

        try:
            oid = place_order(side, order_type, price, quantity)
            print(f"[{name}] placed {order_type} {side} id={oid} price={price} qty={quantity}")
        except Exception as e:
            print(f"[{name}] error placing order: {e}")

        time.sleep(random.uniform(0.1, 0.5))

if __name__ == "__main__":
    t1 = threading.Thread(target=bot, args=("Buyer", "buy"), daemon=True)
    t2 = threading.Thread(target=bot, args=("Seller", "sell"), daemon=True)
    t1.start()
    t2.start()
    print("Simulation started. Press Ctrl-C to stop.")
    while running:
        time.sleep(3)
    print("Stopping simulation...")