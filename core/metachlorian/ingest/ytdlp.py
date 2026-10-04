"""yt-dlp integration for importing videos from web links (YouTube, Vimeo, archive.org, direct links...).

Ported from Cutawan's ``src/main/pipeline/ytdlp.ts`` (same author, MIT): the standalone yt-dlp binary is
downloaded from the official GitHub releases on first use (unless one is configured or on PATH), a failed
run self-updates yt-dlp once per process and retries (sites change their players constantly), the user's
browser login or a cookies.txt file can be borrowed for private videos, and errors come back as a plain
next step rather than an extractor trace.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable

import httpx

from ..config import Settings

ProgressFn = Callable[[float, str], None]   # (fraction 0..1, or -1 for indeterminate; message)
CHROMIUM_BROWSERS = {"chrome", "edge", "brave", "opera", "vivaldi"}
BROWSERS = CHROMIUM_BROWSERS | {"firefox", "safari"}
PLUGIN_DIR = Path(__file__).with_name("ytdlp_plugins")
# Same choice as Cutawan: MP4 video+audio at or below the height cap, else the best single file.
FORMAT = "bv*[height<={h}][ext=mp4]+ba[ext=m4a]/b[height<={h}][ext=mp4]/bv*[height<={h}]+ba/b[height<={h}]/b"
INFO_KEYS = ("id", "title", "uploader", "uploader_id", "channel", "channel_url", "upload_date", "timestamp", "duration",
             "webpage_url", "extractor_key", "license", "description", "tags", "categories", "width", "height", "fps",
             "language", "location", "playlist_title", "playlist_index")


class YtDlpError(Exception):
    """Failure of the yt-dlp process itself (as opposed to our own validation)."""


def _binary_name() -> str:
    if sys.platform.startswith("win"):
        return "yt-dlp.exe"
    if sys.platform == "darwin":
        return "yt-dlp_macos"
    return "yt-dlp_linux_aarch64" if platform.machine().lower() in ("aarch64", "arm64") else "yt-dlp_linux"


def managed_path(settings: Settings) -> Path:
    return settings.data_dir / "bin" / _binary_name()


def find(settings: Settings) -> str | None:
    """The configured executable, else ``yt-dlp`` on PATH, else the copy this library downloaded."""
    for cand in (settings.ytdlp_path, os.environ.get("METACHLORIAN_YTDLP", "")):
        if cand and os.access(cand, os.X_OK):
            return cand
    on_path = shutil.which("yt-dlp")
    if on_path:
        return on_path
    mp = managed_path(settings)
    return str(mp) if os.access(mp, os.X_OK) else None


def ensure(settings: Settings, progress: ProgressFn | None = None) -> str:
    """Path to a working yt-dlp, downloading the official standalone build on first use."""
    found = find(settings)
    if found:
        return found
    dest = managed_path(settings)
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/{_binary_name()}"
    if progress:
        progress(-1, "Downloading yt-dlp (one-time setup)…")
    tmp = dest.with_suffix(".download")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
            if r.status_code >= 400:
                raise YtDlpError(f"Could not download yt-dlp (HTTP {r.status_code}). Check the server's internet connection.")
            total = int(r.headers.get("content-length") or 0)
            seen = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
                    seen += len(chunk)
                    if progress and total:
                        progress(min(1.0, seen / total) * 0.1, "Downloading yt-dlp (one-time setup)…")
    except httpx.HTTPError as e:
        tmp.unlink(missing_ok=True)
        raise YtDlpError(f"Could not download yt-dlp: {e}. Check the server's internet connection, or install yt-dlp.") from e
    os.chmod(tmp, 0o755)
    os.replace(tmp, dest)
    return str(dest)


def version(exe: str) -> str | None:
    try:
        return subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def cookies_file(settings: Settings) -> Path:
    return settings.data_dir / "import-cookies.txt"


def auth_args(settings: Settings) -> list[str]:
    """Borrow a login: an uploaded cookies.txt wins over the browser's cookie store (Cutawan's order)."""
    cf = cookies_file(settings)
    args: list[str] = []
    if cf.exists():
        args = ["--cookies", str(cf)]
    elif settings.import_cookies_browser in BROWSERS:
        args = ["--cookies-from-browser", settings.import_cookies_browser]
    if args and PLUGIN_DIR.exists():
        args = ["--plugin-dirs", str(PLUGIN_DIR), *args]  # reads Chromium cookie stores while the browser is open
    return args


def clean_error(stderr: str) -> str:
    line = next((x for x in reversed(stderr.splitlines()) if x.startswith("ERROR:")), "")
    return re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*[^\s:]*:?\s*)?", "", line).strip()


def is_auth_error(msg: str) -> bool:
    return bool(re.search(r"log ?in|sign ?in|password|private|members only|purchase|cookies|401|403|authori[sz]", msg, re.I))


def is_cookie_copy_error(msg: str) -> bool:
    return bool(re.search(r"could not copy chrome cookie database|permission denied.*cookies", msg, re.I))


def is_dpapi_error(msg: str) -> bool:
    return bool(re.search(r"failed to decrypt with dpapi|cannot decrypt v\d+ cookies|no key found", msg, re.I))


def login_hint(msg: str, settings: Settings) -> str:
    """A next step for errors that come from logins and cookies (wording follows Cutawan)."""
    browser, has_file = settings.import_cookies_browser, cookies_file(settings).exists()
    if is_dpapi_error(msg):
        return ("Windows encrypts Chrome and Edge cookies so other programs cannot read them. Upload a cookies.txt file "
                "(Settings → Imports; export it with the 'Get cookies.txt LOCALLY' extension while signed in) or choose Firefox.")
    if is_cookie_copy_error(msg):
        if has_file:
            return "Your cookies file did not work. Export a fresh one while signed in to the site and upload it again."
        return ("Chromium browsers lock their cookie store while open. Try Firefox, fully quit the browser and retry, "
                "or upload a cookies.txt file (Settings → Imports).")
    if is_auth_error(msg):
        if browser or has_file:
            return (f"The site still refused the login. Make sure you are signed in to it in {browser or 'your browser'} "
                    "(open the video there once), then retry, or upload a fresh cookies.txt file.")
        return ("This video seems to need a login (private, unlisted or behind company sign-in). Sign in to the site in your "
                "browser, then choose that browser or upload a cookies.txt file in Settings → Imports.")
    return ""


_updated = threading.Event()


class Runner:
    """Runs yt-dlp, reporting progress lines and supporting cancellation."""

    def __init__(self, exe: str):
        self.exe = exe
        self.proc: subprocess.Popen | None = None
        self.cancelled = False

    def run(self, args: list[str], on_line: Callable[[str], None] | None = None, timeout: float = 6 * 3600) -> str:
        env = dict(os.environ)
        ff = shutil.which("ffmpeg")
        if ff:
            env["PATH"] = os.path.dirname(ff) + os.pathsep + env.get("PATH", "")
        self.proc = subprocess.Popen([self.exe, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
                                     bufsize=1, start_new_session=True)
        err: list[str] = []
        t = threading.Thread(target=lambda: err.extend(self.proc.stderr), daemon=True)  # type: ignore[union-attr]
        t.start()
        out: list[str] = []
        for line in self.proc.stdout:  # type: ignore[union-attr]
            out.append(line)
            if on_line:
                on_line(line.rstrip("\n"))
        try:
            code = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.cancel()
            raise YtDlpError("yt-dlp took too long") from None
        t.join(5)
        if self.cancelled:
            raise YtDlpError("cancelled")
        if code != 0:
            stderr = "".join(err)[-65536:]
            raise YtDlpError(clean_error(stderr) or f"yt-dlp exited with code {code}")
        return "".join(out)

    def cancel(self) -> None:
        self.cancelled = True
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, 15)
            except (OSError, AttributeError):
                self.proc.terminate()

    def with_self_update(self, fn: Callable[[], Any], progress: ProgressFn | None = None) -> Any:
        """On a yt-dlp failure, run its self-updater once per process and retry (Cutawan's approach).
        A yt-dlp installed by a package manager refuses -U; then the original error stands."""
        try:
            return fn()
        except YtDlpError as e:
            if self.cancelled or _updated.is_set() or is_auth_error(str(e)):
                raise
            _updated.set()
            if progress:
                progress(-1, "Updating yt-dlp…")
            try:
                Runner(self.exe).run(["-U"], timeout=300)
            except YtDlpError:
                raise e from None
            return fn()


def probe(r: Runner, settings: Settings, url: str, playlist: bool) -> list[dict[str, Any]]:
    """What the link holds: one video, or (with ``playlist``) the videos of a playlist or channel."""
    base = ["--no-warnings", *auth_args(settings)]
    if playlist:
        data = json.loads(r.run(["-J", "--flat-playlist", "--yes-playlist", *base, "--", url], timeout=600))
        if data.get("_type") == "playlist":
            out = []
            for e in data.get("entries") or []:
                u = e.get("url") or e.get("webpage_url")
                if u and (e.get("ie_key") or "").lower() != "youtubetab":
                    out.append({"url": u, "title": e.get("title"), "duration": e.get("duration"), "id": e.get("id"),
                                "site": e.get("ie_key") or data.get("extractor_key"), "playlist_title": data.get("title")})
            return out
        return [_entry(data, url)]
    data = json.loads(r.run(["-J", "--no-playlist", *base, "--", url], timeout=600))
    if data.get("_type") == "playlist":
        # e.g. an archive.org item with several files: the longest entry is almost always the main video.
        entries = [e for e in data.get("entries") or [] if (e.get("duration") or 0) > 0]
        if not entries:
            raise YtDlpError("This link does not contain a downloadable video.")
        main = max(entries, key=lambda e: e.get("duration") or 0)
        data = {**main, "title": main.get("title") or data.get("title"), "webpage_url": main.get("url") or main.get("webpage_url")}
    return [_entry(data, url)]


def _entry(data: dict[str, Any], url: str) -> dict[str, Any]:
    if data.get("is_live"):
        raise YtDlpError("This is a live stream; import it once it has finished.")
    return {"url": data.get("webpage_url") or data.get("url") or url, "title": data.get("title") or "Imported video",
            "duration": data.get("duration"), "id": data.get("id"), "site": data.get("extractor_key") or data.get("extractor"),
            "info": {k: data.get(k) for k in INFO_KEYS if data.get(k) not in (None, "", [])}}


def download(r: Runner, settings: Settings, url: str, out_dir: Path, max_height: int, progress: ProgressFn) -> tuple[Path, dict[str, Any]]:
    """Download one video as MP4 into ``out_dir``. Returns the file and its metadata (from yt-dlp's info json)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    marker = "MC_FILE:"

    def on_line(line: str) -> None:
        m = re.search(r"\[download\]\s+([\d.]+)%", line)
        if m:
            progress(0.1 + float(m.group(1)) / 100 * 0.85, "Downloading video…")
        elif "[Merger]" in line or "[VideoConvertor]" in line:
            progress(0.96, "Merging streams…")

    out = r.run(["-f", FORMAT.format(h=int(max_height)), "--merge-output-format", "mp4", "--no-playlist", "--no-warnings",
                 "--newline", "--windows-filenames", "--trim-filenames", "180", "--no-part", "--write-info-json", "--no-mtime",
                 *auth_args(settings), "-o", str(out_dir / "%(title).120B [%(id)s].%(ext)s"),
                 "--print", f"after_move:{marker}%(filepath)s", "--", url], on_line)
    path = next((Path(x.split(marker, 1)[1].strip()) for x in reversed(out.splitlines()) if marker in x), None)
    if not path or not path.exists():
        raise YtDlpError("yt-dlp finished but no video file was written")
    info: dict[str, Any] = {}
    side = path.with_suffix(".info.json")
    if side.exists():
        try:
            full = json.loads(side.read_text())
            info = {k: full.get(k) for k in INFO_KEYS if full.get(k) not in (None, "", [])}
        except json.JSONDecodeError:
            pass
        side.unlink()  # keep the library folder to video files; the metadata lives in the database
    return path, info
