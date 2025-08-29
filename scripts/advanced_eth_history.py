# save as advanced_eth_history.py
import os, csv, asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from coinbase.rest import RESTClient

load_dotenv()

# Prefer CDP vars if present; otherwise fall back to Advanced keys
API_KEY = os.getenv("COINBASE_API_KEY")
API_SECRET = os.getenv("COINBASE_API_SECRET")

# If your CDP key is not the full "organizations/{org}/apiKeys/{key}" or SECRET is not a PEM,
# create Advanced Trade API keys and set COINBASE_API_KEY / COINBASE_API_SECRET instead.

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

async def fetch_all():
    ensure_dir("histories")
    client = RESTClient(api_key=API_KEY, api_secret=API_SECRET) if API_KEY and API_SECRET else RESTClient()

    start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    end = datetime.now(timezone.utc)
    # Coinbase Advanced API limit: < 350 candles per request.
    # 5-minute candles per day = 288, so fetch 1 day per request to stay under the cap.
    chunk_days = 1
    chunks = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=chunk_days), end)
        chunks.append((cur, nxt))
        cur = nxt

    total = 0
    for i, (s, e) in enumerate(chunks, 1):
        print(f"[{i}/{len(chunks)}] {s:%Y-%m-%d} → {e:%Y-%m-%d}")
        # Advanced Trade granularity enum: "FIFTEEN_MINUTE"
        # The SDK accepts epoch seconds for start/end
        candles = client.get_candles(
            product_id="ETH-USD",
            start=int(s.timestamp()),
            end=int(e.timestamp()),
            granularity="FIVE_MINUTE",
        )

        data = getattr(candles, "candles", candles)  # tolerate return shape
        if not data:
            print("  no data")
            continue

        # Normalize and save
        rows = []
        for c in data:
            # c is a Candle object with attributes: start, open, high, low, close, volume
            ts = int(c.start)
            open_ = float(c.open)
            high_ = float(c.high)
            low_ = float(c.low)
            close_ = float(c.close)
            vol = float(c.volume)
            rows.append([
                ts,
                datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                open_, high_, low_, close_, vol
            ])

        fname = f"histories/eth_5min_coinbase_{s:%Y%m%d}_{e:%Y%m%d}.csv"
        with open(fname, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp","datetime","open","high","low","close","volume"])
            w.writerows(sorted(rows, key=lambda r: r[0]))
        print(f"  saved {len(rows)} rows → {fname}")
        total += len(rows)
        # brief delay to respect API rate limits
        await asyncio.sleep(0.2)

    print(f"Done. Total rows: {total}")

if __name__ == "__main__":
    asyncio.run(fetch_all())