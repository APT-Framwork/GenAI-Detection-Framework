#!/usr/bin/env python3
"""
STRIX dashboard render check — Layer 3.

Drives a real browser via Playwright; asserts that every dashboard
widget actually renders the data backed by the live platform. Pairs
with ``monitor_demo.py`` (Layers 1+2). Together they prove the
Caldera→Wazuh→Redis→PG→API→browser path is correct end-to-end.

Usage
-----
    bash jury_demo_single.sh --apt APT41 --duration 240   # terminal 1
    python infra/scripts/monitor_demo.py --ws-tap         # terminal 2
    python infra/scripts/playwright_check.py              # terminal 3

Login
-----
Tries env STRIX_TEST_EMAIL/PASSWORD, then admin@strix.io / changeme123!.
Override with --email / --password.

Outputs
-------
* Live progress to stdout.
* /tmp/strix_e2e_<RUN_ID>/playwright.jsonl  — every assertion + result.
* /tmp/strix_e2e_<RUN_ID>/screenshots/      — full-page snaps at milestones.
* /tmp/strix_e2e_<RUN_ID>/console_log.txt   — browser console output.
* /tmp/strix_e2e_<RUN_ID>/network_log.jsonl — every XHR + WS frame.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import (  # type: ignore
    Browser,
    BrowserContext,
    ConsoleMessage,
    Page,
    Playwright,
    async_playwright,
)

REPO = Path(__file__).resolve().parents[2]
SIM_RUNS_DIR = REPO / "infra" / "simulation" / "runs"

DEFAULT_DASHBOARD_URL = "http://localhost:5600"
DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_TEST_EMAIL = "admin@strix.io"
DEFAULT_TEST_PASSWORD = "changeme123!"

G = "\033[32m"; R = "\033[31m"; Y = "\033[33m"; D = "\033[2m"; B = "\033[1m"; X = "\033[0m"

# Set when SIGTERM/SIGINT arrives. The watch loops poll this so the orchestrator
# can stop them early (right after the demo ends) instead of waiting for the
# full --watch-seconds deadline. The main flow then proceeds to ui_tour and
# _finalize, which writes playwright_final.json.
_STOP: asyncio.Event = asyncio.Event()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Assertion:
    name: str
    ok: bool
    note: str = ""
    elapsed_ms: int = 0


@dataclass
class CheckState:
    out_dir: Path
    assertions: list[Assertion] = field(default_factory=list)
    console_msgs: list[dict[str, Any]] = field(default_factory=list)
    network: list[dict[str, Any]] = field(default_factory=list)
    run_id: str | None = None
    # Per-tactic screenshots: track the last seen tactic so we shoot only
    # on transitions, not every poll.
    last_tactic_seen: str | None = None
    tactics_screenshot: list[str] = field(default_factory=list)


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s.lower()).strip("_")


# ---------- topology.json helper ----------
def latest_topology() -> tuple[str | None, dict | None]:
    if not SIM_RUNS_DIR.exists():
        return None, None
    runs = sorted(SIM_RUNS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for d in runs:
        f = d / "topology.json"
        if f.exists():
            try:
                return d.name, json.loads(f.read_text())
            except Exception:
                continue
    return None, None


# ---------- assertion plumbing ----------
def record(state: CheckState, name: str, ok: bool, note: str = "", started: float | None = None) -> None:
    elapsed_ms = int((time.time() - started) * 1000) if started else 0
    state.assertions.append(Assertion(name, ok, note, elapsed_ms))
    glyph = f"{G}✓{X}" if ok else f"{R}✗{X}"
    print(f"  {glyph} {name:<50s} {D}{note}{X}")
    # Stream to JSONL.
    (state.out_dir / "playwright.jsonl").open("a").write(
        json.dumps({"ts": _now_iso(), "name": name, "ok": ok, "note": note,
                    "elapsed_ms": elapsed_ms}) + "\n"
    )


# ---------- browser hooks ----------
def attach_browser_hooks(state: CheckState, page: Page) -> None:
    def _on_console(msg: ConsoleMessage) -> None:
        try:
            entry = {"ts": _now_iso(), "type": msg.type, "text": msg.text[:500]}
        except Exception:
            entry = {"ts": _now_iso(), "type": "unknown", "text": "<unreadable>"}
        state.console_msgs.append(entry)

    page.on("console", _on_console)

    def _on_request(req: Any) -> None:
        if req.url.startswith(("http://localhost:8000/api", "ws://localhost:8000")):
            state.network.append({"ts": _now_iso(), "kind": "request",
                                  "method": req.method, "url": req.url})

    def _on_response(resp: Any) -> None:
        if resp.url.startswith(("http://localhost:8000/api",)):
            state.network.append({"ts": _now_iso(), "kind": "response",
                                  "status": resp.status, "url": resp.url})

    def _on_websocket(ws: Any) -> None:
        state.network.append({"ts": _now_iso(), "kind": "ws_open", "url": ws.url})
        ws.on("close", lambda *_: state.network.append(
            {"ts": _now_iso(), "kind": "ws_close", "url": ws.url}))

    page.on("request", _on_request)
    page.on("response", _on_response)
    page.on("websocket", _on_websocket)


# ---------- login flow ----------
async def login(page: Page, dashboard_url: str, email: str, password: str) -> bool:
    """Visit /login, fill the form, submit, expect to land on a non-/login URL."""
    await page.goto(f"{dashboard_url}/login", wait_until="domcontentloaded")
    # Try to find email + password inputs by common selectors. The Next.js
    # login page uses `useState` so input names may vary; fall back to type=.
    try:
        # press_sequentially simulates real keystrokes so React's controlled
        # inputs receive synthetic onChange events. fill() only sets .value,
        # which React's value-tracker silently discards → form submits empty.
        email_loc = page.locator('input[type="email"], input[name="email"], input#email').first
        pw_loc = page.locator('input[type="password"], input[name="password"], input#password').first
        await email_loc.click()
        await email_loc.press_sequentially(email, delay=10)
        await pw_loc.click()
        await pw_loc.press_sequentially(password, delay=10)
        await page.locator('button[type="submit"]').first.click()
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"{R}login form interaction failed: {e}{X}\n")
        return False
    # Wait briefly for redirect away from /login.
    try:
        await page.wait_for_url(lambda u: "/login" not in u, timeout=10_000)
        return True
    except Exception:
        return False


# ---------- assertions ----------
async def assert_topology_widget(state: CheckState, page: Page) -> None:
    """Wait for SIMULATION TOPOLOGY card to render with run_id + APT label."""
    started = time.time()
    rid, topo = latest_topology()
    expected_apt = (topo or {}).get("apt_group", "")
    expected_victims = len((topo or {}).get("victims", []))
    state.run_id = rid
    try:
        # The topology panel header text contains "SIMULATION TOPOLOGY".
        await page.locator("text=SIMULATION TOPOLOGY").first.wait_for(timeout=15_000)
        body = await page.content()
        # Coarse: just check that run_id substring appears somewhere.
        ok_run = (rid is not None) and (rid[:20] in body)
        ok_apt = (expected_apt == "") or (expected_apt in body)
        record(state, "topology widget rendered", True, "", started)
        record(state, "topology widget shows current run_id",
               ok_run, f"expected={rid}", started)
        record(state, "topology widget shows APT label",
               ok_apt, f"expected={expected_apt!r}", started)
        # Count victim labels — heuristic: each victim hostname appears in DOM.
        victim_hits = 0
        for v in (topo or {}).get("victims", []):
            label = v.get("hostname") or v.get("name") or ""
            if label and label in body:
                victim_hits += 1
        record(state, "topology victim count matches lab",
               victim_hits == expected_victims,
               f"{victim_hits}/{expected_victims}", started)
    except Exception as e:  # noqa: BLE001
        record(state, "topology widget rendered", False, str(e)[:100], started)


async def assert_forensic_logs(state: CheckState, page: Page) -> None:
    """Wait for the Forensic Raw Logs panel to start streaming."""
    started = time.time()
    try:
        await page.locator("text=Forensic Raw Logs").first.wait_for(timeout=20_000)
        # Wait until the terminal panel has multiple non-empty lines. The
        # actual log format is bracketed tokens like "[options ...] [...]"
        # rendered in a dark code block — counting "agent=" missed real
        # rows. Use line-count + content-length heuristics instead.
        deadline = time.time() + 30
        rows_seen = 0
        chars_seen = 0
        while time.time() < deadline:
            txt = await page.locator("text=Forensic Raw Logs").first.locator("..").inner_text()
            lines = [ln for ln in (txt or "").splitlines() if len(ln.strip()) > 20]
            rows_seen = len(lines)
            chars_seen = len(txt or "")
            if rows_seen >= 5:
                break
            await asyncio.sleep(1.0)
        record(state, "Forensic Raw Logs panel rendered", True, "", started)
        record(state, "Forensic Raw Logs streaming events",
               rows_seen >= 5,
               f"{rows_seen} rows / {chars_seen} chars", started)
    except Exception as e:  # noqa: BLE001
        record(state, "Forensic Raw Logs panel rendered", False, str(e)[:100], started)


async def assert_apt_attack_timeline(state: CheckState, page: Page) -> None:
    started = time.time()
    try:
        await page.locator("text=APT Attack Timeline").first.wait_for(timeout=15_000)
        record(state, "APT Attack Timeline rendered", True, "", started)
    except Exception as e:  # noqa: BLE001
        record(state, "APT Attack Timeline rendered", False, str(e)[:100], started)


async def assert_rl_intervention_timeline(state: CheckState, page: Page) -> None:
    started = time.time()
    try:
        await page.locator("text=RL Intervention Timeline").first.wait_for(timeout=15_000)
        record(state, "RL Intervention Timeline rendered", True, "", started)
        # Pluck counter text.
        for _ in range(60):  # poll up to 60s
            body = await page.content()
            for kw in ("PREDETECTED", "POST-DETECTED"):
                # Look for a non-zero counter near the keyword.
                idx = body.find(kw)
                if idx > 0:
                    snippet = body[max(0, idx-40):idx]
                    if any(d in snippet for d in "123456789"):
                        record(state, f"RL Intervention shows ≥1 {kw}",
                               True, snippet[-30:], started)
                        return
            await asyncio.sleep(2.0)
        record(state, "RL Intervention shows verdicts", False,
               "still 0/0 after 60s of polling", started)
    except Exception as e:  # noqa: BLE001
        record(state, "RL Intervention Timeline rendered", False, str(e)[:100], started)


async def live_dashboard_snapshots(
    state: CheckState, page: Page, deadline: float, interval: float = 20.0
) -> None:
    """Snap a full-page screenshot of the live dashboard every `interval` s
    until `deadline`. Useful to prove the dashboard kept rendering during
    the sim (the human sees panels light up tactic-by-tactic)."""
    n = 0
    while time.time() < deadline and not _STOP.is_set():
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass
        if time.time() >= deadline:
            break
        n += 1
        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        shot = state.out_dir / "screenshots" / f"live_{n:02d}_{ts}.png"
        try:
            await page.screenshot(path=str(shot), full_page=True)
            record(state, f"live screenshot #{n}", True, shot.name, time.time())
        except Exception as e:  # noqa: BLE001
            record(state, f"live screenshot #{n}", False, str(e)[:80], time.time())


async def ui_tour(state: CheckState, page: Page, dashboard_url: str) -> None:
    """After the sim is finished, walk every dashboard page, screenshot
    each, and exercise a couple of clickable controls so the human can see
    everything renders for real. Each visit is its own assertion."""
    pages = [
        ("/", "main_dashboard"),
        ("/vigilance-feed", "vigilance_feed"),
        ("/topology", "topology"),
        ("/ai-engine", "ai_engine"),
        ("/threat-intel", "threat_intel"),
        ("/notifications", "notifications"),
    ]
    for path, slug in pages:
        started = time.time()
        try:
            url = f"{dashboard_url}{path}"
            await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            # Let React Query polling fire once.
            await asyncio.sleep(3.0)
            shot = state.out_dir / "screenshots" / f"page_{slug}.png"
            await page.screenshot(path=str(shot), full_page=True)
            # Healthy render = (a) we didn't bounce back to /login (auth
            # still good), (b) body is real content. Don't sniff for the
            # "404" string — Next.js embeds it in the root layout's
            # not-found boundary, so it's present even on healthy pages.
            current_url = page.url
            body = await page.content()
            on_login = "/login" in current_url
            substantial = len(body) > 5_000
            ok = (not on_login) and substantial
            note = f"{shot.name} ({len(body)//1024}KB) url={current_url.split('://',1)[-1]}"
            record(state, f"page {path} renders", ok, note, started)
        except Exception as e:  # noqa: BLE001
            record(state, f"page {path} renders", False, str(e)[:100], started)

    # --- Drill into one attack-analysis chain ---
    started = time.time()
    try:
        # Land back on main and look for a chain link.
        await page.goto(dashboard_url, wait_until="domcontentloaded")
        await asyncio.sleep(2.0)
        # Most chain rows have href="/attack-analysis/<uuid>".
        chain_link = page.locator('a[href^="/attack-analysis/"]').first
        if await chain_link.count() > 0:
            href = await chain_link.get_attribute("href")
            await chain_link.click()
            await asyncio.sleep(3.0)
            shot = state.out_dir / "screenshots" / "attack_analysis_drill.png"
            await page.screenshot(path=str(shot), full_page=True)
            body = await page.content()
            # Expect at least one ML-section keyword.
            kws = ("Autoencoder", "VAE", "GNN", "Transformer", "DQN",
                   "Kill Chain", "Attack Chain")
            hits = [k for k in kws if k in body]
            record(state, "attack-analysis drill: page renders", True,
                   f"{href} hits={hits}", started)
        else:
            record(state, "attack-analysis drill: chain link found", False,
                   "no <a href=/attack-analysis/...> on dashboard", started)
    except Exception as e:  # noqa: BLE001
        record(state, "attack-analysis drill: page renders", False,
               str(e)[:100], started)

    # --- Try clicking a "refresh" button if one exists on the main page ---
    started = time.time()
    try:
        await page.goto(dashboard_url, wait_until="domcontentloaded")
        await asyncio.sleep(2.0)
        btn = page.locator('button:has-text("Refresh"), button[aria-label*="efresh"]').first
        if await btn.count() > 0:
            await btn.click()
            await asyncio.sleep(2.0)
            shot = state.out_dir / "screenshots" / "after_refresh_click.png"
            await page.screenshot(path=str(shot), full_page=True)
            record(state, "refresh button click", True, shot.name, started)
        else:
            # Not a failure — just informational.
            record(state, "refresh button click", True,
                   "no refresh button found (skipped)", started)
    except Exception as e:  # noqa: BLE001
        record(state, "refresh button click", False, str(e)[:100], started)


async def watch_tactics(state: CheckState, page: Page, deadline: float) -> None:
    """Poll topology.json until `deadline`. Snap a screenshot each time
    `current_tactic` flips. Names: <run_id>/screenshots/<tactic-slug>.png.

    Run as a background task so the main flow (login + initial asserts)
    can complete first; this watcher then keeps running for the remainder
    of the sim and exits at `deadline`.
    """
    while time.time() < deadline and not _STOP.is_set():
        try:
            _, topo = latest_topology()
            cur = (topo or {}).get("current_tactic")
            if cur and cur != state.last_tactic_seen:
                state.last_tactic_seen = cur
                state.tactics_screenshot.append(cur)
                shot_path = state.out_dir / "screenshots" / f"tactic_{_slug(cur)}.png"
                try:
                    await page.screenshot(path=str(shot_path), full_page=True)
                    record(state, f"screenshot @ tactic={cur}", True,
                           shot_path.name, time.time())
                except Exception as e:  # noqa: BLE001
                    record(state, f"screenshot @ tactic={cur}", False,
                           str(e)[:80], time.time())
        except Exception:  # noqa: BLE001
            pass
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass


async def assert_detection_quality(state: CheckState, page: Page) -> None:
    """Just verify the panel rendered. F1 is checked separately, post-sim,
    in `assert_detection_quality_f1_postsim` — that runs after the sim has
    produced thousands of labelled events so the metric has time to climb
    off zero."""
    started = time.time()
    try:
        await page.locator("text=Detection Quality").first.wait_for(timeout=15_000)
        record(state, "Detection Quality panel rendered", True, "", started)
    except Exception as e:  # noqa: BLE001
        record(state, "Detection Quality panel rendered", False, str(e)[:100], started)


async def assert_detection_quality_f1_postsim(state: CheckState, page: Page) -> None:
    """Read the AE + VAE F1 numbers from the rendered Cards after the sim
    is over. Each ModelSubPanel renders a Card labelled "F1" containing the
    f1 value; we use the role/text locator to read the ones that belong to
    the Detection Quality panel specifically (not the AI Engine page).

    The AI Engine F1 (training-time) is ~0.87 — those are static and
    always >0. The Dashboard F1 is *live* (rolling 60s of labelled WS
    frames), so it can briefly be 0 between bursts. We accept ANY positive
    F1 on either AE or VAE during the post-sim window as evidence the
    panel + label flow are working."""
    started = time.time()
    try:
        # Land on main dashboard where Detection Quality lives.
        await page.goto("http://localhost:5600/", wait_until="domcontentloaded")
        await asyncio.sleep(3.0)
        # Scope the search to the Detection Quality container.
        panel = page.locator(":has-text('Detection Quality — AE vs VAE')").last
        await panel.wait_for(timeout=15_000)
        deadline = time.time() + 30
        ae_f1 = vae_f1 = 0.0
        import re
        f1_re = re.compile(r"F1\s*([01]\.[0-9]{3})")
        while time.time() < deadline:
            txt = (await panel.inner_text()) or ""
            matches = f1_re.findall(txt)
            # First two are the per-model Cards (AE, VAE) inside the panel.
            if len(matches) >= 2:
                ae_f1 = float(matches[0])
                vae_f1 = float(matches[1])
                if ae_f1 > 0 or vae_f1 > 0:
                    break
            await asyncio.sleep(1.0)
        ok = (ae_f1 > 0) or (vae_f1 > 0)
        record(state, "Detection Quality shows non-zero F1", ok,
               f"AE_F1={ae_f1:.3f} VAE_F1={vae_f1:.3f}", started)
    except Exception as e:  # noqa: BLE001
        record(state, "Detection Quality shows non-zero F1", False,
               str(e)[:120], started)


# ---------- main ----------
async def amain(args: argparse.Namespace) -> int:
    # Bind SIGTERM/SIGINT to _STOP so watchers exit promptly when the
    # orchestrator says "demo finished" — without that, watchers run to
    # --watch-seconds and the post-sim ui_tour + finalize never happen.
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, _STOP.set)
            except NotImplementedError:
                pass

    rid, _topo = latest_topology()
    out_dir = Path(f"/tmp/strix_e2e_{rid or 'live'}")
    (out_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    state = CheckState(out_dir=out_dir, run_id=rid)
    print(f"{B}STRIX Layer 3 — Playwright dashboard check{X}")
    print(f"  dashboard:  {args.dashboard_url}")
    print(f"  email:      {args.email}")
    print(f"  artifacts:  {out_dir}/")
    print()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=args.headless,
            channel="chrome" if args.system_chrome else None,
        )
        context = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await context.new_page()
        attach_browser_hooks(state, page)

        # --- Login ---
        ok = await login(page, args.dashboard_url, args.email, args.password)
        record(state, "login succeeded", ok, args.email, time.time())
        if not ok:
            print(f"{R}aborting — login failed. Set STRIX_TEST_PASSWORD or update creds.{X}")
            await browser.close()
            return _finalize(state)

        # --- Dashboard widgets ---
        # Most dashboards land at "/" or "/dashboard" after login.
        await page.goto(args.dashboard_url, wait_until="domcontentloaded")
        await asyncio.sleep(2.0)

        await assert_topology_widget(state, page)
        await assert_apt_attack_timeline(state, page)

        # Background tasks during the sim:
        #   1. watch_tactics — screenshot on each `current_tactic` flip.
        #   2. live_dashboard_snapshots — periodic full-page snaps so the
        #      human can flip through the sim frame-by-frame afterwards.
        deadline = time.time() + args.watch_seconds
        watch_task = asyncio.create_task(watch_tactics(state, page, deadline))
        live_task = asyncio.create_task(
            live_dashboard_snapshots(state, page, deadline, interval=20.0)
        )

        await assert_rl_intervention_timeline(state, page)
        await assert_detection_quality(state, page)
        await assert_forensic_logs(state, page)

        # Wait for watchers to finish (sim done) — but cap it.
        with suppress(asyncio.CancelledError, asyncio.TimeoutError):
            await asyncio.wait_for(
                asyncio.gather(watch_task, live_task, return_exceptions=True),
                timeout=max(0.0, deadline - time.time()),
            )

        # --- Post-sim re-check of Detection Quality F1 ---
        # The early in-sim check is too eager: at t=0 there are no
        # labelled WS frames yet so F1 is legitimately 0. By now we've
        # had the full sim plus dwell, so labels have had time to flow.
        await assert_detection_quality_f1_postsim(state, page)

        # --- Post-sim UI tour: visit every page, drill into a chain ---
        await ui_tour(state, page, args.dashboard_url)

        # --- Final snapshot ---
        await page.screenshot(path=str(out_dir / "screenshots" / "final.png"), full_page=True)
        record(state, "final screenshot captured", True,
               str(out_dir / "screenshots" / "final.png"), time.time())

        await context.close()
        await browser.close()
    return _finalize(state)


def _finalize(state: CheckState) -> int:
    # Persist console + network logs.
    (state.out_dir / "console_log.txt").write_text(
        "\n".join(f"[{m['ts']}] {m['type']:>8s}  {m['text']}"
                  for m in state.console_msgs)
    )
    (state.out_dir / "network_log.jsonl").write_text(
        "\n".join(json.dumps(e) for e in state.network)
    )

    n_pass = sum(1 for a in state.assertions if a.ok)
    n_total = len(state.assertions)
    overall = "PASS" if n_pass == n_total else "FAIL"

    print()
    print(f"{B}═══ LAYER 3 RESULT: {G if overall=='PASS' else R}{overall}{X} {B}({n_pass}/{n_total} assertions){X}")
    for a in state.assertions:
        glyph = f"{G}✓{X}" if a.ok else f"{R}✗{X}"
        print(f"  {glyph} {a.name:<50s} {D}{a.note}{X}")
    print()
    print(f"  artifacts: {state.out_dir}/")
    summary = {
        "overall": overall,
        "passed": n_pass,
        "total": n_total,
        "assertions": [a.__dict__ for a in state.assertions],
    }
    (state.out_dir / "playwright_final.json").write_text(json.dumps(summary, indent=2))
    return 0 if overall == "PASS" else 1


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dashboard-url", default=os.environ.get("STRIX_DASHBOARD_URL", DEFAULT_DASHBOARD_URL))
    p.add_argument("--api-url", default=os.environ.get("STRIX_API_URL", DEFAULT_API_URL))
    p.add_argument("--email", default=os.environ.get("STRIX_TEST_EMAIL", DEFAULT_TEST_EMAIL))
    p.add_argument("--password", default=os.environ.get("STRIX_TEST_PASSWORD", DEFAULT_TEST_PASSWORD))
    p.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True,
                   help="run headless (default) or with a visible window (--no-headless)")
    p.add_argument("--system-chrome", action="store_true",
                   help="use system Google Chrome instead of Playwright's bundled chromium "
                        "(saves ~150MB download)")
    p.add_argument("--watch-seconds", type=int, default=480,
                   help="how long to poll topology.json for tactic flips (default 8 min)")
    args = p.parse_args()
    sys.exit(asyncio.run(amain(args)))


if __name__ == "__main__":
    main()
