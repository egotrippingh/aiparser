"""Measure scanner timings against disposable copies of saved browser profiles.

This is deliberately outside the scan/repository path: it calls adapters and
``service_context`` only. Progress writes hashes, never queries, answers, URLs,
cookies, or exception details; private debug artifacts retain failed evidence.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import config
from app.scanner import humanize
from app.scanner.adapters import ADAPTERS
from app.scanner.adapters import alice, chatgpt, google_aio, perplexity
from app.scanner.adapters.base import (AuthRequiredError, CaptchaError, ServiceUnavailableError,
                                       dump_debug_html, dump_debug_screenshot)
from app.scanner.browser import _lock_is_free, service_context

MODULES = {"alice": alice, "chatgpt": chatgpt, "google_aio": google_aio, "perplexity": perplexity}
STOP_ERRORS = (AuthRequiredError, CaptchaError, ServiceUnavailableError)


class InputMismatch(RuntimeError):
    """Humanized typing did not leave the requested query in the input."""


def _safe_detail(exc: Exception) -> str:
    text = str(exc)
    text = re.sub(r"https?://\S+", "<url>", text)
    text = re.sub(r"(?i)\b(token|cookie|authorization|session|secret|api[_ -]?key)\b\s*[:=]\s*\S+", r"\1=<redacted>", text)
    return text[:1200]


def _under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _copy_profiles(source: Path, destination: Path, services: list[str]) -> None:
    if not source.is_dir() or destination.exists() or _under(destination, source) or _under(source, destination):
        raise ValueError("profiles must exist; output must be fresh and neither path may contain the other")
    for service in services:
        profile = source / service
        lock = profile / "parent.lock"
        if not profile.is_dir() or (lock.exists() and not _lock_is_free(lock)):
            raise RuntimeError(f"{service}: missing profile or active parent.lock")
        if any(p.is_symlink() for p in profile.rglob("*")):
            raise RuntimeError(f"{service}: symlinked profile files are unsafe to copy")
    destination.mkdir(parents=True)
    for service in services:
        original, copied = source / service, destination / service
        shutil.copytree(original, copied, ignore=shutil.ignore_patterns(
            "parent.lock", ".parentlock", "lock", "*-wal", "*-shm", "*-journal"))
        for database in original.rglob("*"):
            if database.is_file() and database.suffix in (".sqlite", ".db"):
                reader = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
                writer = sqlite3.connect(copied / database.relative_to(original))
                try:
                    reader.backup(writer)
                finally:
                    writer.close()
                    reader.close()


class Timings:
    def __init__(self):
        self.calls = {"typing": 0, "scroll": 0, "pause": 0, "load_state": 0}
        self.seconds = {key: 0.0 for key in self.calls}

    def reset(self) -> None:
        for values in (self.calls, self.seconds):
            for key in values:
                values[key] = 0

    @contextmanager
    def instrument(self, *, skip_scroll: bool = False):
        originals = {name: getattr(humanize, name) for name in ("type_like_human", "scroll_through", "sleep")}
        def wrap(name, fn):
            async def timed(*args, **kwargs):
                start = time.monotonic(); self.calls[name] += 1
                try:
                    result = await fn(*args, **kwargs)
                    if name == "typing":
                        page, selector = args[:2]
                        expected = str(args[2] if len(args) > 2 else kwargs["text"]).strip()
                        actual = await page.locator(selector).first.evaluate(
                            "el => (el.value ?? el.innerText ?? el.textContent ?? '').trim()")
                        if actual.strip() != expected:
                            raise InputMismatch("input text differs after humanized typing")
                    return result
                finally:
                    self.seconds[name] += time.monotonic() - start
            return timed
        humanize.type_like_human = wrap("typing", originals["type_like_human"])
        if skip_scroll:
            async def skipped_scroll(*args, **kwargs):
                self.calls["scroll"] += 1
            humanize.scroll_through = skipped_scroll
        else:
            humanize.scroll_through = wrap("scroll", originals["scroll_through"])
        humanize.sleep = wrap("pause", originals["sleep"])
        try:
            yield
        finally:
            for name, fn in originals.items():
                setattr(humanize, name, fn)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _outcome(raw_stable: bool, no_overview_stable: bool, source_hash: str, later_hash: str | None) -> tuple[str, bool]:
    source_stable = later_hash is not None and source_hash == later_hash
    if not (raw_stable or no_overview_stable):
        return "raw_changed", source_stable
    if later_hash is None:
        return "sources_unverified", source_stable
    if not source_stable:
        return "sources_changed", source_stable
    return ("no_overview" if no_overview_stable else "verified"), source_stable


async def _raw_digest(page, service: str, *, answer_tab: bool = False) -> tuple[dict | None, str | None]:
    module = MODULES[service]
    if service == "perplexity" and answer_tab:
        try:
            tab = page.get_by_role("tab", name=module._S["tab_answer"], exact=True)
            if not await tab.first.is_visible(timeout=2000):
                return None, "answer_tab_unavailable"
            await tab.first.click(timeout=3000)
        except Exception:
            return None, "answer_tab_unavailable"
    locator = page.locator(module._S["answer_container"])
    locator = locator.last if service == "chatgpt" else locator.first
    try:
        raw = (await locator.inner_text(timeout=5000)).strip()
    except Exception:
        return None, "answer_locator_unavailable"
    return {"chars": len(raw), "sha256": _hash(raw), "text": raw}, None


async def _query(adapter, page, service: str, query: str, speed: float, timings: Timings, screenshot: Path,
                 debug: Path, phase: dict) -> dict:
    timings.reset()
    phases, start = {}, time.monotonic()
    phase["current"] = "ask"
    await adapter.ask(page, query, None, speed=speed)
    phases["ask"] = time.monotonic() - start
    before, before_reason = await _raw_digest(page, service)
    start = time.monotonic()
    phase["current"] = "capture"
    capture = await adapter.capture(page)
    screenshot.write_bytes(capture.screenshot_bytes)
    phases["capture"] = time.monotonic() - start
    start = time.monotonic()
    phase["current"] = "verification"
    await asyncio.sleep(5)
    after, after_reason = await _raw_digest(page, service, answer_tab=True)
    phases["post_verification"] = time.monotonic() - start
    later_sources = None
    if service in ("chatgpt", "google_aio"):
        try:
            later_sources = await adapter._extract_sources(page)
        except Exception:
            pass
    elif service == "alice":
        try:
            seen, collected = set(), []
            for href in await page.locator("a[href^='http']").evaluate_all("els => els.map(e => e.href)"):
                if href not in seen and not alice._is_chrome_link(href):
                    seen.add(href)
                    collected.append(href)
            later_sources = collected
        except Exception:
            pass
    stable = before is not None and after is not None and before == after
    no_overview_stable = (service == "google_aio" and not capture.shown and
                          before_reason == after_reason == "answer_locator_unavailable")
    verification = "stable" if stable else ("no_overview_stable" if no_overview_stable
                                              else before_reason or after_reason or "raw_text_changed")
    source_hash = _hash("\n".join(sorted(capture.sources)))
    later_hash = _hash("\n".join(sorted(later_sources))) if later_sources is not None else None
    outcome, source_stable = _outcome(stable, no_overview_stable, source_hash, later_hash)
    if outcome == "raw_changed":
        debug.mkdir(parents=True, exist_ok=True)
        (debug / "raw-before.txt").write_text(before["text"] if before else "", encoding="utf-8")
        (debug / "raw-after.txt").write_text(after["text"] if after else "", encoding="utf-8")
    before_public = None if before is None else {k: v for k, v in before.items() if k != "text"}
    after_public = None if after is None else {k: v for k, v in after.items() if k != "text"}
    return {"status": "ok" if outcome in ("verified", "no_overview") else "incomplete", "outcome": outcome,
            "phases_sec": phases, "calls": timings.calls.copy(),
            "instrumented_sec": {k: round(v, 3) for k, v in timings.seconds.items()},
            "shown": capture.shown, "raw_before": before_public, "raw_after": after_public,
            "raw_stable": stable, "verification": verification,
            "no_overview_stable": no_overview_stable,
            "sources": {"captured_count": len(capture.sources), "captured_sha256": source_hash,
                        "later_count": len(later_sources) if later_sources is not None else None,
                        "later_sha256": later_hash,
                        "stable": later_sources is not None and source_hash == later_hash}}


async def _run_service(service: str, args, output) -> bool:
    started = time.monotonic()
    try:
        return await _run_service_context(service, args, output)
    except Exception as exc:
        _emit(output, {"service": service, "status": "error", "error": type(exc).__name__,
                       "startup_sec": round(time.monotonic() - started, 3), "stopped": True})
        return False


async def _run_service_context(service: str, args, output) -> bool:
    adapter, timing = ADAPTERS[service], Timings()
    async with service_context(service, headless=args.headless) as context:
        page = context.pages[0] if context.pages else await context.new_page()
        original_wait = page.wait_for_load_state
        async def measured_wait(state="load", **kwargs):
            timing.calls["load_state"] += 1; started = time.monotonic()
            try:
                if args.variant == "candidate" and service == "google_aio" and state == "networkidle":
                    home = google_aio._S["home_url"].rstrip("/")
                    return await page.wait_for_url(lambda url: str(url).rstrip("/") != home and
                        ("/search" in str(url) or "/sorry/" in str(url)), wait_until="domcontentloaded", **kwargs)
                return await original_wait(state, **kwargs)
            finally:
                timing.seconds["load_state"] += time.monotonic() - started
        page.wait_for_load_state = measured_wait
        with timing.instrument(skip_scroll=args.skip_scroll):
            started = time.monotonic(); ready = await adapter.ensure_ready(page)
            prepare = time.monotonic() - started
            if not ready.ok:
                _emit(output, {"service": service, "status": ready.reason or "not_ready", "prepare_sec": round(prepare, 3), "stopped": True})
                return False
            completed = 0
            complete = True
            for round_no in range(args.rounds):
                for number, query in enumerate(args.queries, 1):
                    query_started = time.monotonic()
                    phase = {"current": "ask"}
                    debug = args.debug / service / f"r{round_no + 1}-q{number}"
                    try:
                        shot = args.screenshots / f"{service}-{round_no + 1}-{number}.jpg"
                        record = await asyncio.wait_for(
                            _query(adapter, page, service, query, args.typing, timing, shot, debug, phase), timeout=420)
                    except Exception as exc:
                        debug.mkdir(parents=True, exist_ok=True)
                        (debug / "error.txt").write_text(_safe_detail(exc), encoding="utf-8")
                        try:
                            tag = f"benchmark_{service}_r{round_no + 1}_q{number}"
                            await dump_debug_html(page, tag)
                            await dump_debug_screenshot(page, tag)
                        except Exception:
                            pass
                        record = {"status": "error", "error": type(exc).__name__, "phase": phase["current"],
                                  "elapsed_sec": round(time.monotonic() - query_started, 3),
                                  "stopped": isinstance(exc, STOP_ERRORS) or isinstance(exc, asyncio.TimeoutError)}
                    record.update({"service": service, "round": round_no + 1, "query": number, "prepare_sec": round(prepare, 3)})
                    _emit(output, record)
                    complete &= record["status"] == "ok"
                    if record["status"] != "ok" and record.get("stopped"):
                        return False
                    completed += 1
                    if completed < args.rounds * len(args.queries):
                        own_lo, own_hi = getattr(adapter, "min_delay_sec", (0.0, 0.0))
                        delay_lo, delay_hi = max(args.delay[0], own_lo), max(args.delay[1], own_hi, args.delay[0], own_lo)
                        start = time.monotonic()
                        await humanize.between_queries(completed, lo=delay_lo, hi=delay_hi, break_every=args.break_every)
                        _emit(output, {"service": service, "round": round_no + 1, "query": number,
                                       "status": "pause", "pause_sec": round(time.monotonic() - start, 3),
                                       "delay": [delay_lo, delay_hi]})
            return complete


def _emit(output, record: dict) -> None:
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    print(line, flush=True)
    output.write(line + "\n"); output.flush()


def _revision() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return "unknown"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, default=Path.home() / "AppData/Local/AIParser/profiles")
    parser.add_argument("--output", type=Path, required=False)
    parser.add_argument("--services", nargs="+", default=["chatgpt", "alice", "google_aio"])
    parser.add_argument("--queries", nargs="+", default=["купить крепёж оптом", "поставщик метизов оптом в москве"])
    parser.add_argument("--profile", choices=humanize.PROFILES, default="fast")
    parser.add_argument("--typing", type=float)
    parser.add_argument("--delay", default=None, help="minimum,maximum seconds")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--variant", choices=("baseline", "candidate"), default="baseline")
    parser.add_argument("--skip-scroll", action="store_true", help="experimentally omit adapter post-answer scrolling")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if unknown := set(args.services) - set(ADAPTERS):
        parser.error(f"unknown services: {sorted(unknown)}")
    base = humanize.profile(args.profile)
    args.break_every = int(base["break_every_n"])
    args.typing = args.typing if args.typing is not None else base["typing"]
    try:
        args.delay = tuple(map(float, args.delay.split(","))) if args.delay else (base["delay_min_sec"], base["delay_max_sec"])
        assert len(args.delay) == 2 and 0 <= args.delay[0] <= args.delay[1] and args.typing > 0 and args.rounds > 0
    except (ValueError, AssertionError):
        parser.error("--delay must be min,max; delays, typing, and rounds must be positive")
    return args


async def _self_check() -> None:
    root = Path.cwd().resolve()
    assert _under(root / "child", root) and not _under(root, root / "child")
    assert _hash("same") == _hash("same") and _hash("same") != _hash("other")
    assert _outcome(True, False, _hash(""), None)[0] == "sources_unverified"
    assert _outcome(False, True, _hash(""), _hash(""))[0] == "no_overview"
    original = humanize.type_like_human

    class Input:
        first = None
        def __init__(self, page): self.page = page; self.first = self
        async def evaluate(self, _): return self.page.value
    class Page:
        value = ""
        def locator(self, _): return Input(self)
    async def typing(page, _selector, text, **_):
        if text != "mismatch":
            page.value = text
    humanize.type_like_human = typing
    try:
        with Timings().instrument():
            await humanize.type_like_human(Page(), "#input", "exact")
        assert humanize.type_like_human is typing
        with Timings().instrument():
            try:
                await humanize.type_like_human(Page(), "#input", "mismatch")
            except InputMismatch:
                pass
            else:
                raise AssertionError("typing mismatch was accepted")
    finally:
        humanize.type_like_human = original


async def main() -> None:
    args = _args()
    if args.self_check:
        await _self_check(); return
    if args.output is None:
        raise SystemExit("--output is required")
    if args.output.exists() or _under(args.output, args.profiles) or _under(args.profiles, args.output):
        raise SystemExit("--output must be a fresh path outside --profiles")
    profiles = args.output / "profiles"
    _copy_profiles(args.profiles, profiles, args.services)
    config.PROFILES_DIR = profiles
    config.DEBUG_DIR = args.output / "debug"
    config.DEBUG_DIR.mkdir()
    args.debug = config.DEBUG_DIR
    args.screenshots = args.output / "screenshots"
    args.screenshots.mkdir()
    with (args.output / "progress.jsonl").open("x", encoding="utf-8") as output:
        _emit(output, {"started_at": datetime.now(timezone.utc).isoformat(), "revision": _revision(),
                       "variant": args.variant, "skip_scroll": args.skip_scroll, "services": args.services, "rounds": args.rounds,
                       "query_count": len(args.queries), "profile": args.profile, "typing": args.typing, "delay": args.delay})
        complete = True
        for service in args.services:
            complete &= await _run_service(service, args, output)
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
