"""Tests for plugin vulnerability scanning."""

import pytest

from app.core.plugin.vuln_scan import ScanResult, Vulnerability, VulnScanner


class TestVulnerability:
    def test_creation(self):
        v = Vulnerability(
            id="CVE-2024-1234",
            summary="Test vuln",
            severity="HIGH",
            affected_package="requests",
            affected_version="2.30.0",
            fixed_version="2.31.0",
        )
        assert v.id == "CVE-2024-1234"
        assert v.severity == "HIGH"


class TestScanResult:
    def test_clean(self):
        result = ScanResult(status="clean")
        assert result.max_severity == "clean"
        assert result.critical_count == 0

    def test_with_vulns(self):
        result = ScanResult(
            status="vulnerable",
            vulnerabilities=[
                Vulnerability(id="v1", severity="HIGH", affected_package="a"),
                Vulnerability(id="v2", severity="CRITICAL", affected_package="b"),
                Vulnerability(id="v3", severity="MEDIUM", affected_package="c"),
            ],
        )
        assert result.max_severity == "CRITICAL"
        assert result.critical_count == 1
        assert result.high_count == 1

    def test_to_dict(self):
        result = ScanResult(
            status="vulnerable",
            vulnerabilities=[
                Vulnerability(id="v1", severity="HIGH", affected_package="a", affected_version="1.0"),
            ],
            scanner="test",
        )
        d = result.to_dict()
        assert d["status"] == "vulnerable"
        assert d["vulnerability_count"] == 1
        assert d["max_severity"] == "HIGH"
        assert d["scanner"] == "test"

    def test_empty_vulns(self):
        result = ScanResult(status="clean", vulnerabilities=[])
        assert result.max_severity == "clean"


class TestVulnScanner:
    def setup_method(self):
        self.scanner = VulnScanner()

    def test_scan_missing_scanner_returns_error(self):
        """Without pip-audit installed, should return error status."""
        import shutil
        if shutil.which("pip-audit"):
            pytest.skip("pip-audit is installed")
        result = self.scanner.scan_wheel("/nonexistent.whl")
        assert result.status == "error"

    def test_scan_installed_missing_scanner(self):
        import shutil
        if shutil.which("pip-audit"):
            pytest.skip("pip-audit is installed")
        result = self.scanner.scan_installed("p1")
        assert result.status == "error"
        assert "pip-audit not installed" in result.error

    def test_scan_requirements_missing_scanner(self):
        import shutil
        if shutil.which("pip-audit"):
            pytest.skip("pip-audit is installed")
        result = self.scanner.scan_requirements("/nonexistent/requirements.txt")
        assert result.status == "error"
