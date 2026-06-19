"""Image loader for MAPS TIFF tiles."""

from typing import Any

import numpy as np
import tifffile
from ome_zarr_converters_tools.models._loader import ImageLoaderInterface


class MapsTiffLoader(ImageLoaderInterface):
    """Custom loader for MAPS TIFF tiles.

    Each MAPS tile is a single-plane, single-channel TIFF. The data is loaded
    and reshaped to ``(C, Z, Y, X)`` to match the non-time-series axes produced
    by :func:`ome_zarr_converters_tools.default_axes_builder`.
    """

    file_path: str

    def load_data(self, resource: Any = None) -> np.ndarray:
        """Load the tile data as a ``(C, Z, Y, X)`` numpy array."""
        path = f"{resource}/{self.file_path}" if resource else self.file_path
        image = tifffile.imread(path)
        # MAPS tiles are 2D (Y, X); add singleton C and Z axes.
        return image.reshape(1, 1, *image.shape)

    def find_data_type(self, resource: Any = None) -> str:
        """Return the dtype without loading the full array."""
        path = f"{resource}/{self.file_path}" if resource else self.file_path
        with tifffile.TiffFile(path) as tif:
            return str(tif.pages[0].dtype)
