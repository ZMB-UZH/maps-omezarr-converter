"""A collection of fractal tasks to convert FEI/Thermo Fisher MAPS data to OME-Zarr."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("maps-omezarr-converter")
except PackageNotFoundError:
    __version__ = "uninstalled"

from maps_omezarr_converter.maps import (
    MapsAcquisitionModel,
    convert_maps_to_omezarr,
)

__all__ = [
    "MapsAcquisitionModel",
    "convert_maps_to_omezarr",
]
