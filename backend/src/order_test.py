from orders import place_order, get_open_orders
import time
# place_order("buy", "limit", 101.0, 2.0)
# place_order("sell", "limit", 105.0, 1.5)

# test 2
# place_order("buy", "limit", 105.0, 1.5)
# place_order("sell", "limit", 105.0, 1.5)

# test 3
# place_order("buy", "limit", 110.0, 3.0)
# place_order("sell", "limit", 105.0, 1.0)

## test5
# place_order("sell", "limit", 105.0, 1.0)  # older
# time.sleep(1)
# place_order("sell", "limit", 105.0, 1.0)  # newer
# place_order("buy", "limit", 110.0, 1.0)

## test6

# place_order("sell", "limit", 105.0, 2.0)
# place_order("buy", "market", None, 1.5)

## test 7
# place_order("buy", "limit", 110.0, 2.0)
# place_order("sell", "market", None, 1.5)

## test 8
# place_order("buy", "market", None, 2.0)

## test9
place_order("sell", "limit", 100.0, 1.0)
place_order("sell", "limit", 101.0, 1.0)
place_order("buy", "limit", 110.0, 2.0)


orders = get_open_orders()
for o in orders:
    print(o)
