"""Plugin package — Tool Plugin Sandbox & Supply Chain Governance.

Submodules:
  - manifest: manifest validation + SHA-256 integrity
  - loader: dynamic plugin loading from wheel/zip
  - sandbox: runtime sandbox constraints (network, filesystem, resource limits)
  - registry: plugin registry + Java sync
  - audit: audit trail helper
"""

__all__ = [
    "manifest",
    "loader",
    "sandbox",
    "registry",
    "audit",
]
