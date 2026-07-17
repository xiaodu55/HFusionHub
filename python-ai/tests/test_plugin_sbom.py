"""Tests for plugin SBOM generation."""

import json
import os
import tempfile

from app.core.plugin.sbom import SBOMComponent, SBOMGenerator, SBOMResult


class TestSBOMComponent:
    def test_creation(self):
        comp = SBOMComponent(name="requests", version="2.31.0", purl="pkg:pypi/requests@2.31.0")
        assert comp.name == "requests"
        assert comp.version == "2.31.0"


class TestSBOMResult:
    def test_to_dict(self):
        result = SBOMResult(
            components=[
                SBOMComponent(name="requests", version="2.31.0"),
            ],
            metadata={"source": "test"},
        )
        d = result.to_dict()
        assert d["bomFormat"] == "CycloneDX"
        assert d["specVersion"] == "1.5"
        assert len(d["components"]) == 1
        assert d["components"][0]["name"] == "requests"
        assert d["metadata"]["source"] == "test"

    def test_to_json(self):
        result = SBOMResult(
            components=[SBOMComponent(name="a", version="1.0")],
        )
        j = result.to_json()
        data = json.loads(j)
        assert data["bomFormat"] == "CycloneDX"

    def test_empty_result(self):
        result = SBOMResult()
        d = result.to_dict()
        assert d["components"] == []


class TestSBOMGenerator:
    def setup_method(self):
        self.gen = SBOMGenerator()

    def test_generate_from_requirements(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("requests==2.31.0\n")
            f.write("flask>=2.0\n")
            f.write("# comment\n")
            f.write("\n")
            f.write("click~=8.0\n")
            f.name
            req_path = f.name
        try:
            result = self.gen.generate_from_requirements(req_path)
            assert len(result.components) == 3
            names = [c.name for c in result.components]
            assert "requests" in names
            assert "flask" in names
            assert "click" in names
        finally:
            os.unlink(req_path)

    def test_generate_from_empty_requirements(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("# empty\n")
            req_path = f.name
        try:
            result = self.gen.generate_from_requirements(req_path)
            assert len(result.components) == 0
        finally:
            os.unlink(req_path)

    def test_generate_from_missing_file(self):
        result = self.gen.generate_from_requirements("/nonexistent/requirements.txt")
        assert result.components == []

    def test_parse_requirement_exact(self):
        name, version = SBOMGenerator._parse_requirement("requests==2.31.0")
        assert name == "requests"
        assert version == "2.31.0"

    def test_parse_requirement_gte(self):
        name, version = SBOMGenerator._parse_requirement("flask>=2.0")
        assert name == "flask"
        assert version == "2.0"

    def test_parse_requirement_no_version(self):
        name, version = SBOMGenerator._parse_requirement("requests")
        assert name == "requests"
        assert version == ""

    def test_parse_requirement_compat(self):
        name, version = SBOMGenerator._parse_requirement("click~=8.0")
        assert name == "click"
        assert version == "8.0"
