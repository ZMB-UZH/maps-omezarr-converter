"""
MAPS to OME-Zarr converter
"""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("maps-omezarr-converter")
except PackageNotFoundError:
    __version__ = "uninstalled"