"""Adapters for OSINT tools under external_tools/."""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import sys

from adapters.base import BaseAdapter
from schemas.common import ToolResult

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = ROOT / "external_tools"
BIN = EXTERNAL / "bin"

URL_RE = re.compile(r"https?://[^\s\]\)>\"'\x1b]+")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
HOST_RE = re.compile(r"[\w.-]+\.[a-zA-Z]{2,}")

# Nexfil prints its author links in stdout before scanning — never treat as hits.
NEXFIL_ARTIFACT_URL_FRAGMENTS = (
    "thewhiteh4t",
    "twc1rcle.com",
)


def _username_probe_url(url: str, query: str) -> bool:
    """Keep probe hits that reference the investigated username in the URL path."""
    from services.discovery.attribution import url_references_seed

    low = url.lower()
    if any(fragment in low for fragment in NEXFIL_ARTIFACT_URL_FRAGMENTS):
        return False
    if "search.php" in low and "author=" in low:
        return False
    return url_references_seed(url, query)


def _clean_url(url: str) -> str:
    return ANSI_RE.sub("", url).strip().rstrip(".,)")


def _tool_root(name: str) -> Path:
    return EXTERNAL / name


def _bin(name: str) -> Path | None:
    for candidate in (BIN / name, BIN / f"{name}.exe"):
        if candidate.is_file():
            return candidate
    if name == "phoneinfoga":
        for candidate in (
            ROOT / "phoneNumber" / "phoneinfoga" / "bin" / "phoneinfoga",
            ROOT / "phoneNumber" / "phoneinfoga" / "bin" / "phoneinfoga.exe",
        ):
            if candidate.is_file():
                return candidate
    return None


def _completed_result(
    tool: str,
    results: list[dict],
    *,
    ran_ok: bool,
    stdout: str = "",
    stderr: str = "",
    fail_error: str | None = None,
    raw_limit: int = 1500,
) -> ToolResult:
    if not ran_ok:
        err = (stderr or stdout or fail_error or "Tool failed").strip()
        if "Traceback" in err:
            err = err.split("Traceback")[0].strip() or fail_error or "Tool failed"
        return ToolResult(
            tool=tool,
            success=False,
            data=results,
            error=err[:300],
            raw_output=stdout[:raw_limit],
        )
    return ToolResult(
        tool=tool,
        success=True,
        data=results,
        error=None,
        raw_output=stdout[:raw_limit],
    )


class BlackbirdAdapter(BaseAdapter):
    name = "blackbird"
    default_timeout = 90.0

    def _load_results_from_disk(self, query: str) -> list[dict]:
        root = _tool_root("blackbird")
        json_files = sorted(root.glob(f"{query}_*_blackbird.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not json_files:
            return []
        try:
            payload = json.loads(json_files[0].read_text())
        except (json.JSONDecodeError, OSError):
            return []
        results: list[dict] = []
        for item in payload if isinstance(payload, list) else []:
            if item.get("status") == "FOUND" and item.get("url"):
                results.append(
                    self._normalize_entry(
                        platform=str(item.get("name") or "unknown"),
                        url=str(item["url"]),
                        extra={"verified": False, "check_type": "username_probe", "status": "unconfirmed"},
                    )
                )
        return results

    async def _execute(self, query: str) -> ToolResult:
        root = _tool_root("blackbird")
        script = root / "blackbird.py"
        if not script.exists():
            return ToolResult(tool=self.name, success=False, error="Blackbird not found")

        cmd = [sys.executable, str(script), "-u", query, "--json", "--timeout", "6", "--no-update"]
        rc, stdout, stderr = await self._run_subprocess(cmd, cwd=str(root))

        results = self._load_results_from_disk(query)
        ran_ok = rc == 0 and ("Check completed" in stdout or bool(results))
        if not ran_ok and results:
            return ToolResult(
                tool=self.name,
                success=True,
                data=results,
                error=None,
                raw_output=(stdout[:1500] or f"Partial Blackbird results ({len(results)} hits)"),
            )
        if not ran_ok:
            return ToolResult(
                tool=self.name,
                success=False,
                data=results,
                error=stderr[:300] or stdout[:300] or "Blackbird failed",
                raw_output=stdout[:1500],
            )

        return ToolResult(
            tool=self.name,
            success=True,
            data=results,
            error=None,
            raw_output=stdout[:1500] or ("No accounts found for this username" if not results else stdout[:1500]),
        )


class NexfilAdapter(BaseAdapter):
    name = "nexfil"
    default_timeout = 90.0

    async def _execute(self, query: str) -> ToolResult:
        cmd = ["nexfil", "-u", query, "-t", "12"]
        rc, stdout, stderr = await self._run_subprocess(cmd)
        combined = f"{stdout}\n{stderr}"
        if "Traceback" in combined or "undetected_chromedriver" in combined or "Chrome Driver" in combined:
            return ToolResult(
                tool=self.name,
                success=False,
                data=[],
                error="Nexfil Chrome driver unavailable — install Chrome/Chromium for this tool",
                raw_output=combined[:1500],
            )
        results = self._parse_urls(stdout, query)
        return _completed_result(
            self.name,
            results,
            ran_ok=rc == 0 and bool(results),
            stdout=stdout,
            stderr=stderr,
            fail_error="Nexfil found no profiles for this username",
        )

    def _parse_urls(self, stdout: str, query: str) -> list[dict]:
        results: list[dict] = []
        seen: set[str] = set()
        for raw_url in URL_RE.findall(stdout):
            url = _clean_url(raw_url)
            if not url.startswith("http") or url in seen:
                continue
            if not _username_probe_url(url, query):
                continue
            seen.add(url)
            host = HOST_RE.search(url)
            platform = host.group(0) if host else "web"
            results.append(
                self._normalize_entry(
                    platform=platform,
                    url=url,
                    extra={"verified": False, "check_type": "username_probe", "status": "unconfirmed"},
                )
            )
        return results


class GitFiveAdapter(BaseAdapter):
    name = "gitfive"
    default_timeout = 90.0

    async def _execute(self, query: str) -> ToolResult:
        root = _tool_root("GitFive")
        script = root / "main.py"
        if not script.exists():
            return ToolResult(tool=self.name, success=False, error="GitFive not found")

        out_path = Path(f"/tmp/gitfive_{query}.json")
        cmd = [sys.executable, str(script), "user", query, "--json", str(out_path)]
        rc, stdout, stderr = await self._run_subprocess(cmd, cwd=str(root))
        if rc != 0 and not out_path.exists():
            err = (stderr or stdout or "GitFive failed").strip()
            if "Traceback" in err:
                err = err.split("Traceback")[0].strip() or "GitFive failed (check GitHub auth: gitfive login)"
            err = err[:300]
            return ToolResult(tool=self.name, success=False, error=err, raw_output=stdout[:500])

        results: list[dict] = []
        if out_path.exists():
            try:
                payload = json.loads(out_path.read_text())
                results.extend(self._parse_json(payload, query))
            except (json.JSONDecodeError, OSError):
                pass

        if not results:
            results = self._parse_stdout(stdout, query)

        return _completed_result(
            self.name,
            results,
            ran_ok=rc == 0 or out_path.exists() or bool(stdout.strip()),
            stdout=stdout,
            stderr=stderr,
            fail_error="GitFive failed",
        )

    def _parse_json(self, payload: Any, query: str) -> list[dict]:
        results: list[dict] = []
        if isinstance(payload, dict):
            profile_url = payload.get("profile_url") or f"https://github.com/{query}"
            results.append(
                self._normalize_entry(
                    platform="github",
                    url=str(profile_url),
                    extra={
                        "handle": query,
                        "verified": True,
                        "check_type": "live_scan",
                        "profile_metadata": payload,
                    },
                )
            )
            for email in payload.get("emails") or []:
                if isinstance(email, str) and "@" in email:
                    results.append(
                        self._normalize_entry(platform="email", extra={"email": email, "source": "gitfive"})
                    )
        return results

    def _parse_stdout(self, stdout: str, query: str) -> list[dict]:
        if "github.com" in stdout.lower() or query.lower() in stdout.lower():
            return [
                self._normalize_entry(
                    platform="github",
                    url=f"https://github.com/{query}",
                    extra={"handle": query, "verified": False, "check_type": "username_probe"},
                )
            ]
        return []


class GhuntAdapter(BaseAdapter):
    name = "ghunt"
    default_timeout = 90.0

    def verify_tool(self) -> tuple[bool, str | None]:
        from services.ghunt_session import ghunt_session_available

        if not ghunt_session_available():
            return False, None
        return super().verify_tool()

    async def _execute(self, query: str) -> ToolResult:
        from services.ghunt_session import ghunt_session_available

        if not ghunt_session_available():
            return ToolResult(tool=self.name, success=True, data=[], error=None, raw_output="Skipped — GHunt login not configured")

        if "@" not in query:
            return ToolResult(tool=self.name, success=False, error="GHunt requires an email address")

        root = _tool_root("GHunt")
        script = root / "main.py"
        if not script.exists():
            return ToolResult(tool=self.name, success=False, error="GHunt not found")

        safe_query = re.sub(r"[^\w.-]", "_", query)
        out_path = Path(tempfile.gettempdir()) / f"ghunt_{safe_query}.json"
        cmd = ["python3", str(script), "email", query, "--json", str(out_path)]
        rc, stdout, stderr = await self._run_subprocess(cmd, cwd=str(root))

        results: list[dict] = []
        if out_path.exists():
            try:
                payload = json.loads(out_path.read_text())
                results.extend(self._parse_json(payload, query))
            except (json.JSONDecodeError, OSError):
                pass

        combined = stderr + stdout
        if "ModuleNotFoundError" in combined:
            missing = re.search(r"No module named '([^']+)'", combined)
            dep = missing.group(1) if missing else "dependency"
            return ToolResult(
                tool=self.name,
                success=False,
                error=f"GHunt missing Python package '{dep}'. Run: pip install -e external_tools/GHunt",
                raw_output=combined[:1500],
            )

        if rc != 0 and "Traceback" in combined:
            return _completed_result(
                self.name,
                results,
                ran_ok=False,
                stdout=stdout,
                stderr=stderr,
                fail_error="GHunt failed",
            )

        if results or "Gaia" in stdout:
            return ToolResult(
                tool=self.name,
                success=True,
                data=results,
                error=None,
                raw_output=stdout[:1500],
            )

        return ToolResult(
            tool=self.name,
            success=True,
            data=[],
            error=None,
            raw_output=stdout[:1500] or "No Google profile linked to this email",
        )

    def _parse_json(self, payload: Any, query: str) -> list[dict]:
        results: list[dict] = []
        if isinstance(payload, dict):
            results.append(
                self._normalize_entry(
                    platform="google",
                    extra={"email": query, "verified": False, "profile_metadata": payload},
                )
            )
        return results


class GravatarAdapter(BaseAdapter):
    name = "gravatar"
    default_timeout = 30.0

    async def _execute(self, query: str) -> ToolResult:
        if "@" not in query:
            return ToolResult(tool=self.name, success=False, error="Gravatar requires an email address")

        from services.email_intel import fetch_gravatar_profile

        profile = await fetch_gravatar_profile(query)
        if not profile:
            return ToolResult(tool=self.name, success=True, data=[], raw_output="No Gravatar profile")

        entry = self._normalize_entry(
            platform="gravatar",
            url=str(profile.get("profile_url") or profile.get("avatar_url") or ""),
            extra={
                "email": query,
                "verified": True,
                "check_type": "live_scan",
                "registered": True,
                "display_name": profile.get("display_name"),
                "avatar_url": profile.get("avatar_url"),
                "bio": profile.get("about") or profile.get("bio"),
                "about": profile.get("about"),
                "location": profile.get("location"),
                "website": profile.get("website"),
                "accounts": profile.get("accounts"),
                "profile_metadata": profile,
            },
        )
        return ToolResult(tool=self.name, success=True, data=[entry], raw_output="Gravatar profile found")


class PhoneinfogaAdapter(BaseAdapter):
    name = "phoneinfoga"
    default_timeout = 90.0

    async def _execute(self, query: str) -> ToolResult:
        from services.phone_intelligence.phoneinfoga_scan import cli_url_rows, run_phoneinfoga_tool
        from services.phone_intelligence.runtime import ensure_phone_stack

        await asyncio.to_thread(ensure_phone_stack)
        result = await asyncio.to_thread(run_phoneinfoga_tool, query)

        cli_supplement = os.getenv("PHONEINFOGA_CLI_SUPPLEMENT", "false").lower() in ("1", "true", "yes")
        if not cli_supplement:
            return result

        binary = _bin("phoneinfoga")
        cli_urls: list[dict[str, Any]] = []
        cli_stdout = ""
        if binary:
            phone = re.sub(r"[^\d+]", "", query.strip())
            if phone:
                cmd = [str(binary), "scan", "-n", phone if phone.startswith("+") else f"+{phone}"]
                rc, stdout, stderr = await self._run_subprocess(cmd)
                cli_stdout = stdout or ""
                if rc == 0 or stdout.strip():
                    cli_urls = cli_url_rows(query, cli_stdout)

        if not result.success and cli_urls:
            return ToolResult(
                tool=self.name,
                success=True,
                data=cli_urls,
                raw_output=f"PhoneInfoga API unavailable — {len(cli_urls)} CLI URL(s) from scan output",
            )
        if result.success and cli_stdout and not any(
            r.get("check_type") == "cli_web_search" for r in (result.data or [])
        ):
            result.data = [*list(result.data or []), *cli_urls]
        return result


class SubfinderAdapter(BaseAdapter):
    name = "subfinder"
    default_timeout = 90.0

    async def _execute(self, query: str) -> ToolResult:
        binary = _bin("subfinder")
        if not binary:
            return ToolResult(tool=self.name, success=False, error="Subfinder binary not found")

        domain = query.strip().lower().split("@")[-1] if "@" in query else query.strip().lower()
        cmd = [str(binary), "-d", domain, "-silent"]
        rc, stdout, stderr = await self._run_subprocess(cmd)

        results: list[dict] = []
        seen: set[str] = set()
        for line in stdout.splitlines():
            host = line.strip().lower()
            if not host or host in seen:
                continue
            seen.add(host)
            results.append(
                self._normalize_entry(
                    platform="subdomain",
                    url=f"https://{host}",
                    extra={"hostname": host, "source_domain": domain},
                )
            )

        return _completed_result(
            self.name,
            results,
            ran_ok=rc == 0 or bool(stdout.strip()) or not stderr.strip(),
            stdout=stdout,
            stderr=stderr,
            fail_error="Subfinder failed",
            raw_limit=2000,
        )


class AmassAdapter(BaseAdapter):
    name = "amass"
    default_timeout = 120.0

    async def _execute(self, query: str) -> ToolResult:
        binary = _bin("amass")
        if not binary:
            return ToolResult(tool=self.name, success=False, error="Amass binary not found")

        domain = query.strip().lower().split("@")[-1] if "@" in query else query.strip().lower()
        cmd = [str(binary), "enum", "-passive", "-d", domain]
        rc, stdout, stderr = await self._run_subprocess(cmd)

        results: list[dict] = []
        seen: set[str] = set()
        for line in stdout.splitlines():
            host = line.strip().lower()
            if not host or " " in host or host in seen:
                continue
            if not HOST_RE.fullmatch(host):
                continue
            seen.add(host)
            results.append(
                self._normalize_entry(
                    platform="subdomain",
                    url=f"https://{host}",
                    extra={"hostname": host, "source_domain": domain},
                )
            )

        return _completed_result(
            self.name,
            results,
            ran_ok=rc == 0 or bool(stdout.strip()) or not stderr.strip(),
            stdout=stdout,
            stderr=stderr,
            fail_error="Amass failed",
            raw_limit=2000,
        )


class DnsreconAdapter(BaseAdapter):
    name = "dnsrecon"
    default_timeout = 90.0

    async def _execute(self, query: str) -> ToolResult:
        root = _tool_root("dnsrecon")
        script = root / "dnsrecon.py"
        if not script.exists():
            return ToolResult(tool=self.name, success=False, error="DNSRecon not found")

        domain = query.strip().lower().split("@")[-1] if "@" in query else query.strip().lower()
        cmd = ["python3", str(script), "-d", domain, "-t", "std"]
        rc, stdout, stderr = await self._run_subprocess(cmd, cwd=str(root))

        results: list[dict] = []
        seen: set[str] = set()
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            for host in HOST_RE.findall(line):
                if host == domain or host in seen:
                    continue
                seen.add(host)
                results.append(
                    self._normalize_entry(
                        platform="dns",
                        url=f"https://{host}",
                        extra={"hostname": host, "source_domain": domain, "record": line[:200]},
                    )
                )

        return _completed_result(
            self.name,
            results,
            ran_ok=rc == 0 or bool(stdout.strip()) or not stderr.strip(),
            stdout=stdout,
            stderr=stderr,
            fail_error="DNSRecon failed",
            raw_limit=2000,
        )


class WhoisAdapter(BaseAdapter):
    name = "whois"
    default_timeout = 45.0

    async def _execute(self, query: str) -> ToolResult:
        domain = query.strip().lower().split("@")[-1] if "@" in query else query.strip().lower()
        results: list[dict] = []

        try:
            import whois

            record = await asyncio.to_thread(whois.whois, domain)
            org = getattr(record, "org", None) or getattr(record, "registrar", None)
            emails = record.emails if hasattr(record, "emails") else None
            if org:
                results.append(
                    self._normalize_entry(
                        platform="organization",
                        extra={"organization": str(org), "source_domain": domain},
                    )
                )
            if emails:
                for email in emails if isinstance(emails, list) else [emails]:
                    if email and "@" in str(email):
                        results.append(
                            self._normalize_entry(platform="email", extra={"email": str(email), "source_domain": domain})
                        )
        except Exception as exc:
            return ToolResult(tool=self.name, success=False, error=f"WHOIS lookup failed: {exc}")

        return ToolResult(
            tool=self.name,
            success=True,
            data=results,
            error=None,
        )


EXTERNAL_OSINT_ADAPTERS: dict[str, type[BaseAdapter]] = {
    "blackbird": BlackbirdAdapter,
    "nexfil": NexfilAdapter,
    "ghunt": GhuntAdapter,
    "gravatar": GravatarAdapter,
    "phoneinfoga": PhoneinfogaAdapter,
    "subfinder": SubfinderAdapter,
    "amass": AmassAdapter,
    "dnsrecon": DnsreconAdapter,
    "whois": WhoisAdapter,
}
