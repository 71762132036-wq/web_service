"""
Cross-expiry GEX validation study for Nifty.
Run: python scripts/analyse_expiries.py
"""
import sys, statistics
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", encoding="utf-8-sig")

from core.config import DATA_DIR
from services.upstox_service import get_available_files
from services.historical_service import get_daily_study

files_dict = get_available_files("Nifty", data_dir=DATA_DIR)
expiries = sorted(files_dict.keys())
print("Nifty expiries:", expiries)
print()

all_days = []

for exp in expiries:
    data = get_daily_study("Nifty", exp)
    if "error" in data or not data.get("days"):
        continue
    s = data["summary"]
    n_days = s["total_days"]
    cw = s["call_wall_held_pct"]
    pw = s["put_wall_held_pct"]
    ir = s["in_range_pct"]
    ra = s["regime_accuracy_pct"]
    print(f"  {exp} | {n_days:2d} days | CW:{cw:5.1f}% PW:{pw:5.1f}% Range:{ir:5.1f}% Regime:{ra:5.1f}%")

    exp_dt = datetime.strptime(exp, "%Y-%m-%d")

    for d in data["days"]:
        m = d["morning"]
        o = d["outcome"]
        try:
            day_int = int(d["day"])
            if day_int > exp_dt.day:
                prev_month = exp_dt.month - 1
                prev_year = exp_dt.year
                if prev_month == 0:
                    prev_month, prev_year = 12, exp_dt.year - 1
                file_date = datetime(prev_year, prev_month, day_int)
            else:
                file_date = datetime(exp_dt.year, exp_dt.month, day_int)
            dte = (exp_dt - file_date).days
        except Exception:
            dte = -1

        all_days.append({
            "expiry":        exp,
            "day":           d["day"],
            "dte":           dte,
            "regime":        m["regime"],
            "call_wall":     m["top_call_wall"],
            "put_wall":      m["top_put_wall"],
            "flip":          m["flip_point"],
            "spot_open":     m["spot"],
            "max_pain":      m["max_pain"],
            "high":          o["high"],
            "low":           o["low"],
            "close":         o["close"],
            "range_pts":     o["range_pts"],
            "call_wall_held":   o["call_wall_held"],
            "put_wall_held":    o["put_wall_held"],
            "stayed_in_range":  o["stayed_in_range"],
            "regime_accurate":  o["regime_accurate"],
            "range_ratio_pct":  o["range_ratio_pct"],
            "price_direction":  o["price_direction"],
        })

n = len(all_days)
print()
print("=" * 60)
print(f"TOTAL DAYS ACROSS ALL EXPIRIES: {n}")
print("=" * 60)

if n == 0:
    sys.exit()

cw = sum(1 for d in all_days if d["call_wall_held"])
pw = sum(1 for d in all_days if d["put_wall_held"])
ir = sum(1 for d in all_days if d["stayed_in_range"])
ra = sum(1 for d in all_days if d["regime_accurate"])

print()
print("OVERALL (all expiries):")
print(f"  Call wall held   : {cw}/{n} = {cw/n*100:.1f}%")
print(f"  Put wall held    : {pw}/{n} = {pw/n*100:.1f}%")
print(f"  Stayed in range  : {ir}/{n} = {ir/n*100:.1f}%")
print(f"  Regime accurate  : {ra}/{n} = {ra/n*100:.1f}%")
print(f"  Avg intraday range: {statistics.mean(d['range_pts'] for d in all_days):.0f} pts")

# ── By Regime ────────────────────────────────────────────────────────────────
print()
print("BY REGIME:")
for regime in ["LONG GAMMA", "SHORT GAMMA"]:
    bucket = [d for d in all_days if d["regime"] == regime]
    if not bucket:
        continue
    b_ir = sum(1 for d in bucket if d["stayed_in_range"])
    b_ra = sum(1 for d in bucket if d["regime_accurate"])
    b_cw = sum(1 for d in bucket if d["call_wall_held"])
    b_pw = sum(1 for d in bucket if d["put_wall_held"])
    avg_r = statistics.mean(d["range_pts"] for d in bucket)
    avg_dir = statistics.mean(abs(d["price_direction"]) for d in bucket)
    print(f"  {regime:12s}: {len(bucket):2d} days | in-range {b_ir/len(bucket)*100:.1f}% | "
          f"CW {b_cw/len(bucket)*100:.1f}% | PW {b_pw/len(bucket)*100:.1f}% | "
          f"regime-ok {b_ra/len(bucket)*100:.1f}% | avg range {avg_r:.0f}pts | avg move {avg_dir:.0f}pts")

# ── By DTE Bucket ────────────────────────────────────────────────────────────
print()
print("BY DAYS-TO-EXPIRY (DTE):")
dte_buckets = [(0, 2, "DTE 0-2  (expiry week)"),
               (3, 5, "DTE 3-5  (near expiry)"),
               (6, 9, "DTE 6-9  (mid expiry) "),
               (10, 30, "DTE 10+  (far expiry) ")]
for lo, hi, label in dte_buckets:
    bucket = [d for d in all_days if lo <= d["dte"] <= hi]
    if not bucket:
        continue
    b_ir = sum(1 for d in bucket if d["stayed_in_range"])
    b_cw = sum(1 for d in bucket if d["call_wall_held"])
    b_pw = sum(1 for d in bucket if d["put_wall_held"])
    avg_r = statistics.mean(d["range_pts"] for d in bucket)
    print(f"  {label}: {len(bucket):2d} days | in-range {b_ir/len(bucket)*100:.1f}% | "
          f"CW {b_cw/len(bucket)*100:.1f}% | PW {b_pw/len(bucket)*100:.1f}% | avg range {avg_r:.0f}pts")

# ── Max Pain on Expiry Day ────────────────────────────────────────────────────
print()
print("MAX PAIN ACCURACY (DTE 0-2, expiry day/eve):")
exp_days = [d for d in all_days if d["dte"] <= 2]
max_pain_errors = []
for d in exp_days:
    dist = abs(d["close"] - d["max_pain"])
    dist_pct = dist / d["max_pain"] * 100
    max_pain_errors.append(dist_pct)
    pin = "PINNED" if dist_pct < 0.5 else ("NEAR" if dist_pct < 1.0 else "MISS")
    print(f"  {d['expiry']} DTE={d['dte']} | Close:{d['close']:.0f} "
          f"MaxPain:{d['max_pain']:.0f} | Dist:{dist:.0f}pts ({dist_pct:.2f}%) | {pin}")

if max_pain_errors:
    pinned = sum(1 for e in max_pain_errors if e < 0.5)
    near   = sum(1 for e in max_pain_errors if e < 1.0)
    print(f"  --> Pinned (<0.5%): {pinned}/{len(max_pain_errors)} = {pinned/len(max_pain_errors)*100:.0f}%")
    print(f"  --> Near   (<1.0%): {near}/{len(max_pain_errors)} = {near/len(max_pain_errors)*100:.0f}%")
    print(f"  --> Avg distance  : {statistics.mean(max_pain_errors):.2f}%")

# ── Wall Break Behaviour ──────────────────────────────────────────────────────
print()
print("WHEN WALLS BREAK (breakout analysis):")
cw_breaks = [d for d in all_days if not d["call_wall_held"]]
pw_breaks = [d for d in all_days if not d["put_wall_held"]]
if cw_breaks:
    avg_ov = statistics.mean(d["high"] - d["call_wall"] for d in cw_breaks)
    print(f"  Call wall broke: {len(cw_breaks)} times | avg overshoot above wall: {avg_ov:.0f}pts")
if pw_breaks:
    avg_un = statistics.mean(d["put_wall"] - d["low"] for d in pw_breaks)
    print(f"  Put wall broke : {len(pw_breaks)} times | avg undershoot below wall: {avg_un:.0f}pts")

# ── Flip Point Distance Distribution ─────────────────────────────────────────
print()
print("FLIP POINT PROXIMITY (spot vs flip at open):")
flip_dists = [abs(d["spot_open"] - d["flip"]) / d["flip"] * 100 for d in all_days]
very_close  = sum(1 for x in flip_dists if x < 0.2)
close       = sum(1 for x in flip_dists if x < 0.5)
print(f"  Within 0.2% of flip: {very_close}/{n} = {very_close/n*100:.0f}%")
print(f"  Within 0.5% of flip: {close}/{n} = {close/n*100:.0f}%")
print(f"  Avg distance: {statistics.mean(flip_dists):.2f}%")
print(f"  When very close (<0.2%): {very_close} days -- high uncertainty, avoid large positions")
