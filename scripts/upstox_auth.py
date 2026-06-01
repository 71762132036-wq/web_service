# -*- coding: utf-8 -*-
"""
scripts/upstox_auth.py — Automated Upstox OAuth token refresh.

Local usage  (visible browser, updates .env + GitHub secret):
    python scripts/upstox_auth.py

GitHub Actions (headless, writes token to /tmp/upstox_token.txt):
    HEADLESS=true python scripts/upstox_auth.py

Required env vars (local: read from .env | CI: GitHub Secrets):
    UPSTOX_PHONE        - 10-digit mobile number
    UPSTOX_PIN          - 6-digit Upstox PIN
    UPSTOX_TOTP_SECRET  - TOTP secret key
"""

import io
import os
import re
import sys
import time
import subprocess
from pathlib import Path

# Force UTF-8 stdout so print() never crashes on Windows cp1252 terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── Load .env when running locally ───────────────────────────────────────────
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file, encoding="utf-8-sig")

# ── Config ────────────────────────────────────────────────────────────────────
PHONE        = os.environ.get("UPSTOX_PHONE", "").strip()
PIN          = os.environ.get("UPSTOX_PIN", "").strip()
TOTP_SECRET  = os.environ.get("UPSTOX_TOTP_SECRET", "").strip()
HEADLESS     = os.environ.get("HEADLESS", "false").lower() == "true"

CLIENT_ID    = "f749999f-e82c-4443-9122-ac07d7a0f5d6"
CLIENT_SECRET= "sbt1wg4ean"
REDIRECT_URI = "https://127.0.0.1:8080/callback"
AUTH_URL     = (
    "https://api.upstox.com/v2/login/authorization/dialog"
    f"?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
)
TOKEN_URL    = "https://api.upstox.com/v2/login/authorization/token"


# ── Step 1: Browser login → auth code ────────────────────────────────────────

def get_auth_code() -> str:
    import pyotp
    from playwright.sync_api import sync_playwright

    auth_code = [None]

    def intercept(route):
        url = route.request.url
        if "code=" in url:
            match = re.search(r'[?&]code=([^&]+)', url)
            if match and not auth_code[0]:
                auth_code[0] = match.group(1)
                # No print here — avoid any encoding risk inside Playwright callback
        route.abort()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            slow_mo=0 if HEADLESS else 350,
        )
        ctx = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()

        # Intercept both the intermediate Upstox redirect AND the final callback
        ctx.route("https://api-v2.upstox.com/login/authorization/redirect*", intercept)
        ctx.route("https://127.0.0.1*", intercept)

        print("  Navigating to Upstox auth page...")
        page.goto(AUTH_URL, timeout=30_000)
        page.wait_for_timeout(2000)

        # ── Mobile ────────────────────────────────────────────────────────────
        print("  Filling mobile number...")
        page.wait_for_selector("#mobileNum", timeout=15_000, state="visible")
        page.fill("#mobileNum", PHONE)
        page.wait_for_timeout(300)
        page.click('button:has-text("Get OTP")')
        page.wait_for_timeout(2500)

        # ── TOTP — wait for a fresh window if code is about to expire ─────────
        totp = pyotp.TOTP(TOTP_SECRET)
        remaining = 30 - (int(time.time()) % 30)
        if remaining < 6:
            print(f"  TOTP expires in {remaining}s — waiting for next window...")
            time.sleep(remaining + 1)
        otp_code = totp.now()
        print(f"  Filling TOTP: {otp_code}")

        page.wait_for_selector("#otpNum", timeout=15_000, state="visible")
        page.fill("#otpNum", otp_code)
        page.wait_for_timeout(300)
        page.click('button:has-text("Continue")')
        page.wait_for_timeout(2500)

        # ── PIN ───────────────────────────────────────────────────────────────
        print("  Filling PIN...")
        page.wait_for_selector("#pinCode", timeout=15_000, state="visible")
        page.fill("#pinCode", PIN)
        page.wait_for_timeout(300)
        page.click('button:has-text("Continue")')

        # ── Wait for redirect capture (max 20s) ───────────────────────────────
        print("  Waiting for redirect...")
        deadline = time.time() + 20
        while time.time() < deadline and not auth_code[0]:
            page.wait_for_timeout(300)

        browser.close()

    if auth_code[0]:
        print(f"  Auth code captured: {auth_code[0][:8]}...")
    else:
        raise RuntimeError("Auth code not captured — login may have failed or selectors changed")

    return auth_code[0]


# ── Step 2: Exchange auth code → access token ─────────────────────────────────

def exchange_token(code: str) -> str:
    import requests

    resp = requests.post(
        TOKEN_URL,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise ValueError(f"Token exchange failed: {data}")
    return data["access_token"]


# ── Step 3a (local): call at.ps1 to update .env + GitHub secret ───────────────

def update_local(token: str) -> None:
    at_ps1 = Path(__file__).resolve().parent.parent / "at.ps1"
    if not at_ps1.exists():
        print(f"  WARNING: at.ps1 not found at {at_ps1}")
        return
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(at_ps1), token],
        capture_output=False,
    )
    if result.returncode != 0:
        print(f"  WARNING: at.ps1 exited with code {result.returncode}")


# ── Step 3b (CI): write token to file for GitHub Actions steps to consume ─────

def write_ci_output(token: str) -> None:
    out = Path("/tmp/upstox_token.txt")
    out.write_text(token)
    print(f"  Token written to {out}")

    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a") as f:
            f.write(f"UPSTOX_ACCESS_TOKEN={token}\n")
        print("  Token exported to GITHUB_ENV")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    missing = [v for v in ("UPSTOX_PHONE", "UPSTOX_PIN", "UPSTOX_TOTP_SECRET")
               if not os.environ.get(v, "").strip()]
    if missing:
        print(f"FAILED - missing env vars: {', '.join(missing)}")
        sys.exit(1)

    print("\n=== Upstox Token Refresh ===")
    print(f"  Mode  : {'headless (CI)' if HEADLESS else 'visible browser (local)'}")
    print(f"  Phone : {PHONE[:4]}****{PHONE[-2:]}\n")

    try:
        print("[1/3] Browser login...")
        code = get_auth_code()

        print("\n[2/3] Token exchange...")
        token = exchange_token(code)
        print(f"  Token: {token[:50]}...")

        print("\n[3/3] Saving token...")
        if HEADLESS:
            write_ci_output(token)
        else:
            update_local(token)

        print("\nDone - token refreshed successfully\n")

    except Exception as exc:
        print(f"\nFAILED: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
