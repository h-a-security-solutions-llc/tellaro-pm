"""Scan local Claude Code installation for available skills and agent profiles."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path


class SkillDiscovery:
    """Discovers Claude Code capabilities, skills, and agent profiles on the local machine."""

    def __init__(self, executable: str) -> None:
        self._executable = executable

    async def scan_skills(self) -> list[dict[str, str]]:
        """Run Claude Code to discover available skills / slash commands.

        Returns a list of dicts, each with at least a ``name`` key and an optional
        ``description`` key.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                self._executable,
                "--help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await asyncio.wait_for(process.communicate(), timeout=15.0)
            stdout_text = stdout_bytes.decode("utf-8", errors="replace")
            return self._parse_help_output(stdout_text)
        except FileNotFoundError:
            print(f"[discovery] Claude executable not found: {self._executable}")
            return []
        except TimeoutError:
            print("[discovery] Timed out running claude --help")
            return []
        except OSError as exc:
            print(f"[discovery] Error running claude --help: {exc}")
            return []

    async def scan_agent_profiles(self) -> list[dict[str, str]]:
        """Look for .claude/ directory configs and CLAUDE.md files in common locations.

        Scans the user's home directory and the current working directory.
        """
        profiles: list[dict[str, str]] = []
        search_roots = [
            Path.home(),
            Path.cwd(),
        ]

        for root in search_roots:
            # Check for .claude/ directory
            claude_dir = root / ".claude"
            if claude_dir.is_dir():
                profiles.append({
                    "type": "claude_directory",
                    "path": str(claude_dir),
                    "source": str(root),
                })
                # Look for config files inside
                for config_file in claude_dir.iterdir():
                    if config_file.is_file() and config_file.suffix in (".json", ".yml", ".yaml", ".toml", ".md"):
                        profiles.append({
                            "type": "claude_config_file",
                            "path": str(config_file),
                            "name": config_file.name,
                        })

            # Check for CLAUDE.md
            claude_md = root / "CLAUDE.md"
            if claude_md.is_file():
                try:
                    content = claude_md.read_text(encoding="utf-8")[:2000]  # cap at 2KB for transport
                    profiles.append({
                        "type": "claude_md",
                        "path": str(claude_md),
                        "content_preview": content,
                    })
                except OSError:
                    profiles.append({
                        "type": "claude_md",
                        "path": str(claude_md),
                        "content_preview": "(unreadable)",
                    })

        return profiles

    async def get_capabilities(self) -> dict[str, object]:
        """Return a structured capabilities payload for backend registration.

        Includes skills list, agent profiles, and Claude Code version.
        """
        skills, profiles, version = await asyncio.gather(
            self.scan_skills(),
            self.scan_agent_profiles(),
            self._get_claude_version(),
        )
        return {
            "skills": skills,
            "profiles": profiles,
            "claude_version": version,
            "platform": os.name,
        }

    # -- Internal helpers ----------------------------------------------------

    async def _get_claude_version(self) -> str:
        """Attempt to detect the installed Claude Code version."""
        try:
            process = await asyncio.create_subprocess_exec(
                self._executable,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await asyncio.wait_for(process.communicate(), timeout=10.0)
            return stdout_bytes.decode("utf-8", errors="replace").strip()
        except (FileNotFoundError, TimeoutError, OSError):
            return "unknown"

    @staticmethod
    def _parse_help_output(text: str) -> list[dict[str, str]]:
        """Best-effort parse of ``claude --help`` output into skill entries."""
        skills: list[dict[str, str]] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("-"):
                continue
            # Heuristic: lines that look like "command  description"
            parts = stripped.split(None, 1)
            if len(parts) == 2:
                skills.append({"name": parts[0], "description": parts[1]})
            elif len(parts) == 1 and len(parts[0]) < 40:
                skills.append({"name": parts[0], "description": ""})
        return skills
