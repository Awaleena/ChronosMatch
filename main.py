import argparse
import asyncio
import time
from chronosmatch.engine import MatchingEngine
from chronosmatch.ledger import TradeLedger
from chronosmatch.ring_buffer import MMapRingBuffer
from chronosmatch.simulator import generate_orders
from chronosmatch.dashboard import run_dashboard

async def run(args):
    bus_path = args.bus
    engine = MatchingEngine()
    ledger = TradeLedger(args.ledger)
    bus = MMapRingBuffer(bus_path, capacity=args.capacity, create=True)
    stats = {"received": 0, "matched": 0, "latencies_ns": [], "started_ns": time.perf_counter_ns()}
    try:
        async for order in generate_orders(args.orders, args.rate):
            # Fixed-size order record is written to mmap, then read back by the consumer.
            while not bus.write(order):
                # In a production design, use a condition/event or separate producer process.
                await asyncio.sleep(0)
            received = bus.read()
            if received is None:
                continue
            stats["received"] += 1
            start = time.perf_counter_ns()
            trades = engine.submit(received)
            elapsed = time.perf_counter_ns() - start
            stats["latencies_ns"].append(elapsed)
            if trades:
                for trade in trades:
                    ledger.record(trade)
                    stats["matched"] += 1
            if args.dashboard and stats["received"] % args.refresh_every == 0:
                run_dashboard(engine, stats, args.orders)
        if args.dashboard:
            run_dashboard(engine, stats, args.orders, final=True)
    finally:
        bus.close()
        ledger.close()

def main():
    parser = argparse.ArgumentParser(description="ChronosMatch educational simulated matching engine")
    parser.add_argument("--orders", type=int, default=10000, help="Number of mock orders to generate")
    parser.add_argument("--rate", type=float, default=0, help="Optional delay between orders in seconds; 0 = as fast as possible")
    parser.add_argument("--capacity", type=int, default=4096, help="Ring buffer capacity (number of records)")
    parser.add_argument("--bus", default="chronosmatch.mmap", help="Path for mmap bus file")
    parser.add_argument("--ledger", default="trades.csv", help="CSV file for completed trades")
    parser.add_argument("--dashboard", action="store_true", help="Print a live-ish terminal dashboard")
    parser.add_argument("--refresh-every", type=int, default=500, help="Refresh dashboard every N orders")
    args = parser.parse_args()
    if args.orders < 1 or args.capacity < 2:
        parser.error("--orders must be >= 1 and --capacity must be >= 2")
    asyncio.run(run(args))

if __name__ == "__main__":
    main()
