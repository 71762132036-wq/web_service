# -*- coding: utf-8 -*-
"""
scripts/upstox_auth.py — Automated Upstox OAuth token refresh.

Local  : python scripts/upstox_auth.py
CI     : HEADLESS=true python scripts/upstox_auth.py

Env vars (local → .env | CI → GitHub Secrets):
    UPSTOX_PHONE       - 10-digit mobile number
    UPSTOX_PIN         - 6-digit PIN
    UPSTOX_TOTP_SECRET - TOTP secret key
"""

import io
import os
import re
import sys
import time
import subprocess
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file, encoding="utf-8-sig")

PHONE       = os.environ.get("UPSTOX_PHONE", "").strip()
PIN         = os.environ.get("UPSTOX_PIN", "").strip()
TOTP_SECRET = os.environ.get("UPSTOX_TOTP_SECRET", "").strip()
HEADLESS    = os.environ.get("HEADLESS", "false").lower() == "true"

CLIENT_ID     = "f749999f-e82c-4443-9122-ac07d7a0f5d6"
CLIENT_SECRET = "sbt1wg4ean"
REDIRECT_URI  = "https://127.0.0.1:8080/callback"
AUTH_URL      = (
    "https://api.upstox.com/v2/login/authorization/dialog"
    f"?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
)
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"


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
        route.abort()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=0 if HEADLESS else 350)
        ctx  = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()

        ctx.route("https://api-v2.upstox.com/login/authorization/redirect*", intercept)
        ctx.route("https://127.0.0.1*", intercept)

        print("  Navigating...")
        page.goto(AUTH_URL, timeout=30_000)
        page.wait_for_timeout(2000)

        print("  Filling mobile...")
        page.wait_for_selector("#mobileNum", timeout=15_000, state="visible")
        page.fill("#mobileNum", PHONE)
        page.wait_for_timeout(300)
        page.click('button:has-text("Get OTP")')
        page.wait_for_timeout(2500)

        totp = pyotp.TOTP(TOTP_SECRET)
        remaining = 30 - (int(time.time()) % 30)
        if remaining < 6:
            print(f"  TOTP window ending in {remaining}s — waiting...")
            time.sleep(remaining + 1)
        otp_code = totp.now()
        print(f"  Filling TOTP: {otp_code}")
        page.wait_for_selector("#otpNum", timeout=15_000, state="visible")
        page.fill("#otpNum", otp_code)
        page.wait_for_timeout(300)
        page.click('button:has-text("Continue")')
        page.wait_for_timeout(2500)

        print("  Filling PIN...")
        page.wait_for_selector("#pinCode", timeout=15_000, state="visible")
        page.fill("#pinCode", PIN)
        page.wait_for_timeout(300)
        page.click('button:has-text("Continue")')

        print("  Waiting for redirect...")
        deadline = time.time() + 20
        while time.time() < deadline and not auth_code[0]:
            page.wait_for_timeout(300)

        browser.close()

    if not auth_code[0]:
        raise RuntimeError("Auth code not captured")
    print(f"  Code: {auth_code[0][:8]}...")
    return auth_code[0]


def exchange_token(code: str) -> str:
    import requests
    resp = requests.post(TOKEN_URL, headers={
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }, data={
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise ValueError(f"Token exchange failed: {data}")
    return data["access_token"]


def save_ci(token: str) -> None:
    """Export token to GITHUB_ENV so the next workflow step can use it."""
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a") as f:
            f.write(f"NEW_ACCESS_TOKEN={token}\n")
        print("  Token exported to GITHUB_ENV")
    else:
        print(f"  {token}")   # fallback: just print it


def save_local(token: str) -> None:
    """Call at.ps1 — updates .env + GitHub secret."""
    at_ps1 = Path(__file__).resolve().parent.parent / "at.ps1"
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(at_ps1), token],
        check=False,
    )


def main():
    missing = [v for v in ("UPSTOX_PHONE", "UPSTOX_PIN", "UPSTOX_TOTP_SECRET")
               if not os.environ.get(v, "").strip()]
    if missing:
        print(f"FAILED - missing: {', '.join(missing)}")
        sys.exit(1)

    print(f"\n=== Upstox Token Refresh ({'CI' if HEADLESS else 'local'}) ===\n")
    try:
        print("[1/3] Login...")
        code = get_auth_code()

        print("\n[2/3] Exchange...")
        token = exchange_token(code)
        print(f"  Token: {token[:50]}...")

        print("\n[3/3] Save...")
        if HEADLESS:
            save_ci(token)
        else:
            save_local(token)

        print("\nDone.\n")
    except Exception as exc:
        print(f"\nFAILED: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
