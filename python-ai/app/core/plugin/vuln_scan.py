"""Vulnerability scanning for plugin dependencies.

Scans plugin wheels and installed dependencies against OSV database
for known vulnerabilities.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Vulnerability:
    id: str
    alias: str = ""
    summary: str = ""
    severity: str = "UNKNOWN"
    affected_package: str = ""
    affected_version: str = ""
    fixed_version: str = ""
    reference_url: str = ""


@dataclass
class ScanResult:
    status: str = "clean"  # clean | vulnerable | error
    vulnerabilities: List[Vulnerability] = field(default_factory=list)
    scan_time: float = 0.0
    scanner: str = "unknown"
    error: Optional[str] = None

    @property
    def max_severity(self) -> str:
        severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
        if not self.vulnerabilities:
            return "clean"
        return max(self.vulnerabilities, key=lambda v: severity_order.get(v.severity, 0)).severity

    @property
    def critical_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == "CRITICAL")

    @property
    def high_count(self) -> int:
        return sum(1 for v in self.vulnerabilities if v.severity == "HIGH")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "vulnerability_count": len(self.vulnerabilities),
            "critical": self.critical_count,
            "high": self.high_count,
            "max_severity": self.max_severity,
            "scanner": self.scanner,
            "vulnerabilities": [
                {
                    "id": v.id,
                    "alias": v.alias,
                    "summary": v.summary,
                    "severity": v.severity,
                    "package": v.affected_package,
                    "affected_version": v.affected_version,
                    "fixed_version": v.fixed_version,
                    "reference": v.reference_url,
                }
                for v in self.vulnerabilities
            ],
        }


class VulnScanner:
    """Scan plugin dependencies for known vulnerabilities."""

    def scan_wheel(self, wheel_path: str) -> ScanResult:
        """Scan a wheel file using pip-audit."""
        import time
        start = time.monotonic()

        try:
            result = subprocess.run(
                ["pip-audit", "--format", "json", "--desc", wheel_path],
                capture_output=True,
                text=True,
                timeout=120,
            )
            elapsed = time.monotonic() - start
            if result.returncode == 0:
                return ScanResult(status="clean", scan_time=elapsed, scanner="pip-audit")

            try:
                data = json.loads(result.stdout)
                vulns = []
                for item in data:
                    for v in item.get("vulns", []):
                        vulns.append(Vulnerability(
                            id=v.get("id", ""),
                            alias=v.get("aliases", [""])[0] if v.get("aliases") else "",
                            summary=v.get("description", ""),
                            severity=v.get("fix_versions", [""])[0] if v.get("fix_versions") else "UNKNOWN",
                            affected_package=item.get("name", ""),
                            affected_version=item.get("version", ""),
                            fixed_version=", ".join(v.get("fix_versions", [])),
                        ))
                return ScanResult(
                    status="vulnerable" if vulns else "clean",
                    vulnerabilities=vulns,
                    scan_time=elapsed,
                    scanner="pip-audit",
                )
            except json.JSONDecodeError:
                return ScanResult(status="error", error="Failed to parse pip-audit output", scan_time=elapsed)
        except FileNotFoundError:
            return self._scan_fallback(wheel_path)
        except subprocess.TimeoutExpired:
            return ScanResult(status="error", error="Scan timed out", scanner="pip-audit")

    def scan_installed(self, plugin_id: str) -> ScanResult:
        """Scan installed plugin dependencies using pip-audit."""
        import time
        start = time.monotonic()

        try:
            result = subprocess.run(
                ["pip-audit", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            elapsed = time.monotonic() - start

            if result.returncode == 0:
                return ScanResult(status="clean", scan_time=elapsed, scanner="pip-audit")

            try:
                data = json.loads(result.stdout)
                vulns = []
                for item in data:
                    for v in item.get("vulns", []):
                        vulns.append(Vulnerability(
                            id=v.get("id", ""),
                            alias=v.get("aliases", [""])[0] if v.get("aliases") else "",
                            summary=v.get("description", ""),
                            severity="MEDIUM",
                            affected_package=item.get("name", ""),
                            affected_version=item.get("version", ""),
                            fixed_version=", ".join(v.get("fix_versions", [])),
                        ))
                return ScanResult(
                    status="vulnerable" if vulns else "clean",
                    vulnerabilities=vulns,
                    scan_time=elapsed,
                    scanner="pip-audit",
                )
            except json.JSONDecodeError:
                return ScanResult(status="error", error="Failed to parse pip-audit output", scan_time=elapsed)
        except FileNotFoundError:
            logger.warning("pip-audit not available, skipping vulnerability scan")
            return ScanResult(status="error", error="pip-audit not installed", scanner="fallback")
        except subprocess.TimeoutExpired:
            return ScanResult(status="error", error="Scan timed out", scanner="pip-audit")

    def scan_requirements(self, requirements_path: str) -> ScanResult:
        """Scan a requirements.txt file."""
        import time
        start = time.monotonic()

        try:
            result = subprocess.run(
                ["pip-audit", "--requirement", requirements_path, "--format", "json"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            elapsed = time.monotonic() - start

            if result.returncode == 0:
                return ScanResult(status="clean", scan_time=elapsed, scanner="pip-audit")

            try:
                data = json.loads(result.stdout)
                vulns = []
                for item in data:
                    for v in item.get("vulns", []):
                        vulns.append(Vulnerability(
                            id=v.get("id", ""),
                            affected_package=item.get("name", ""),
                            affected_version=item.get("version", ""),
                            fixed_version=", ".join(v.get("fix_versions", [])),
                        ))
                return ScanResult(
                    status="vulnerable" if vulns else "clean",
                    vulnerabilities=vulns,
                    scan_time=elapsed,
                    scanner="pip-audit",
                )
            except json.JSONDecodeError:
                return ScanResult(status="error", scan_time=elapsed, scanner="pip-audit")
        except FileNotFoundError:
            return ScanResult(status="error", error="pip-audit not installed", scanner="fallback")
        except subprocess.TimeoutExpired:
            return ScanResult(status="error", error="Scan timed out", scanner="pip-audit")

    def _scan_fallback(self, wheel_path: str) -> ScanResult:
        """Fallback: report as unknown since we can't scan."""
        logger.warning("No vulnerability scanner available, reporting unknown status")
        return ScanResult(status="error", error="No scanner available", scanner="none")
