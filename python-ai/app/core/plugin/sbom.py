"""SBOM generation for plugin wheels — CycloneDX format.

Generates Software Bill of Materials from plugin wheel files to track
dependencies and enable vulnerability scanning.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SBOMComponent:
    name: str
    version: str
    purl: str = ""
    license_id: str = ""
    description: str = ""
    hash_value: str = ""
    hash_alg: str = "SHA-256"


@dataclass
class SBOMResult:
    format: str = "cyclonedx-json"
    version: str = "1.5"
    spec_version: str = "1.5"
    components: list[SBOMComponent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bomFormat": "CycloneDX",
            "specVersion": self.spec_version,
            "version": 1,
            "metadata": {
                "tools": [{"vendor": "HFusionHub", "name": "plugin-sbom-generator"}],
                **self.metadata,
            },
            "components": [
                {
                    "type": "library",
                    "name": c.name,
                    "version": c.version,
                    "purl": c.purl or f"pkg:pypi/{c.name}@{c.version}",
                    "licenses": [{"id": c.license_id}] if c.license_id else [],
                    "description": c.description,
                    "hashes": [{"alg": c.hash_alg, "content": c.hash_value}] if c.hash_value else [],
                }
                for c in self.components
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class SBOMGenerator:
    """Generate SBOM for plugin wheels."""

    def generate_from_wheel(self, wheel_path: str) -> SBOMResult:
        """Generate SBOM from a wheel file using cyclonedx-py."""
        try:
            result = subprocess.run(
                ["cyclonedx-py", "environment", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=os.path.dirname(wheel_path) or ".",
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return self._parse_cyclonedx(data)
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("cyclonedx-py not available, using fallback: %s", e)

        return self._generate_fallback(wheel_path)

    def generate_from_requirements(self, requirements_path: str) -> SBOMResult:
        """Generate SBOM from a requirements.txt file."""
        try:
            with open(requirements_path) as f:
                lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

            components = []
            for line in lines:
                name, version = self._parse_requirement(line)
                if name:
                    components.append(SBOMComponent(
                        name=name,
                        version=version or "0.0.0",
                        purl=f"pkg:pypi/{name}@{version or '0.0.0'}",
                    ))

            return SBOMResult(
                components=components,
                metadata={"source": requirements_path},
            )
        except Exception as e:
            logger.error("Failed to generate SBOM from requirements: %s", e)
            return SBOMResult()

    def _generate_fallback(self, wheel_path: str) -> SBOMResult:
        """Fallback SBOM using pkginfo or filename parsing."""
        components = []
        basename = os.path.basename(wheel_path)
        parts = basename.replace(".whl", "").split("-")
        if len(parts) >= 2:
            components.append(SBOMComponent(
                name=parts[0],
                version=parts[1],
                purl=f"pkg:pypi/{parts[0]}@{parts[1]}",
            ))

        return SBOMResult(
            components=components,
            metadata={"source": wheel_path, "generator": "fallback"},
        )

    def _parse_cyclonedx(self, data: dict[str, Any]) -> SBOMResult:
        result = SBOMResult()
        for comp in data.get("components", []):
            hashes = comp.get("hashes", [])
            hash_val = hashes[0].get("content", "") if hashes else ""
            hash_alg = hashes[0].get("alg", "SHA-256") if hashes else ""
            result.components.append(SBOMComponent(
                name=comp.get("name", ""),
                version=comp.get("version", ""),
                purl=comp.get("purl", ""),
                license_id=comp.get("licenses", [{}])[0].get("id", "") if comp.get("licenses") else "",
                description=comp.get("description", ""),
                hash_value=hash_val,
                hash_alg=hash_alg,
            ))
        return result

    @staticmethod
    def _parse_requirement(line: str) -> tuple:
        for op in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            if op in line:
                parts = line.split(op, 1)
                return parts[0].strip(), parts[1].strip()
        return line.strip(), ""
