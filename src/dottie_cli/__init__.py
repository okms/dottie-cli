"""Dottie CLI package."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("dottie-cli")
except PackageNotFoundError:  # pragma: no cover - source tree without installed metadata
    __version__ = "0+unknown"
