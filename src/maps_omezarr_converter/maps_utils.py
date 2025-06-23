"""Tools to convert MAPS acquisitions to ome-zarr."""

from collections.abc import Generator, Sequence
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import numpy as np
import tifffile
from fractal_converters_tools import (
    OriginDict,
    Point,
    SimplePathBuilder,
    Tile,
    TiledImage,
    Vector,
)
from lxml import etree
from ngio import PixelSize


class mapsTileLoader:
    """maps tile loader."""

    def __init__(self, path: str):
        """Initialize mapsTileLoader."""
        self.path = path

    @property
    def dtype(self):
        """Get the data type of the tile."""
        with tifffile.TiffFile(self.path) as tif:
            dtype = tif.pages[0].dtype
        return dtype

    def load(self) -> np.ndarray:
        """Load the tile data."""
        image = tifffile.imread(self.path)
        return image.reshape(*(1, 1, 1), *image.shape)


def _get_stage_position(
    tif_path: Path, transformMatrix: np.ndarray
) -> tuple[float, float]:
    tif = tifffile.TiffFile(tif_path)
    root = ET.fromstring(tif.pages[0].tags["FEI_TITAN"].value)
    stage_pos_x = (
        float(root.find("StageSettings").find("StagePosition").find("X").text) * 10**6
    )
    stage_pos_y = (
        float(root.find("StageSettings").find("StagePosition").find("Y").text) * 10**6
    )
    stage_pos_x, stage_pos_y = np.dot(
        transformMatrix, np.array([stage_pos_x, stage_pos_y])
    )
    return stage_pos_x, -stage_pos_y


def _get_grid_position(tif_path: Path) -> tuple[float, float]:
    name = tif_path.stem
    y_idx, x_idx = name.split("_")[1].split("-")[:2]
    return int(x_idx), int(y_idx)


def _build_tiles(
    tif_list: Sequence[Path], metadata_dict: dict, gridmode: bool = False
) -> Generator[Tile, Any, None]:
    """Build tiles from a list of TIFF files."""
    tif = tifffile.TiffFile(tif_list[0])
    root = ET.fromstring(tif.pages[0].tags["FEI_TITAN"].value)
    # shape
    shape_x = tif.pages[0].tags["ImageWidth"].value
    shape_y = tif.pages[0].tags["ImageLength"].value

    # scale factors [um]/[px]
    scale_x = float(root.find("BinaryResult").find("PixelSize").find("X").text) * 10**6
    scale_y = float(root.find("BinaryResult").find("PixelSize").find("Y").text) * 10**6

    # [um]
    length_x = shape_x * scale_x
    length_y = shape_y * scale_y

    # rotation
    if metadata_dict is None or "angle_deg" not in metadata_dict:
        # Default to 0 degrees if no metadata is provided
        metadata_dict = {"angle_deg": 0.0}
    angle = -np.deg2rad(metadata_dict["angle_deg"])
    transformMatrix = np.array(
        [
            [np.cos(angle), -np.sin(angle)],
            [np.sin(angle), np.cos(angle)],
        ]
    )

    for tif_path in tif_list:
        stage_pos_x, stage_pos_y = _get_stage_position(tif_path, transformMatrix)
        if gridmode:
            grid_pos_x, grid_pos_y = _get_grid_position(tif_path)
            top_l = Point(
                x=grid_pos_x,
                y=grid_pos_y,
                z=0,
                c=0,
                t=0,
            )
        else:
            top_l = Point(
                x=stage_pos_x,
                y=stage_pos_y,
                z=0,
                c=0,
                t=0,
            )

        diag = Vector(x=length_x, y=length_y, z=1, c=1, t=1)
        tile_loader = mapsTileLoader(path=tif_path)
        pixel_size = PixelSize(x=scale_x, y=scale_y, z=1)
        origin = OriginDict(
            x_micrometer_original=stage_pos_x,
            y_micrometer_original=stage_pos_y,
            z_micrometer_original=0,
            t_original=0,
        )
        tile = Tile(
            top_l=top_l,
            diag=diag,
            pixel_size=pixel_size,
            origin=origin,
            data_loader=tile_loader,
        )
        yield tile


def _build_tiled_image(
    tif_list: Sequence[Path],
    zarr_name: str,
    metadata_dict: dict | None = None,
    gridmode: bool = False,
) -> TiledImage:
    """Build tiled image from a list of TIFF files."""
    tiled_image = TiledImage(
        name=zarr_name,
        path_builder=SimplePathBuilder(path=zarr_name),
        channel_names=["C00"],
        wavelength_ids=["C00"],
    )
    for tile in _build_tiles(tif_list, metadata_dict, gridmode):
        tiled_image.add_tile(tile)

    return tiled_image


def _parse_maps_metadata(project_path: str | Path, acquisition_name: str) -> dict:
    """Parse MAPS metadata from the project XML file.

    (Currently only rotation angle).
    This is probably not at all robust, but it works for the current MAPS
    project XML structure.
    """
    xml_path = Path(project_path) / "MapsProject.xml"
    if not Path(xml_path).exists():
        raise FileNotFoundError(f"Project XML not found: {project_path}")

    tree = etree.parse(xml_path)
    root = tree.getroot()
    namespaces = {
        "ns0": "http://schemas.datacontract.org/2004/07/Fei.Applications.Perseus.Project"
    }
    folder_path = f"LayersData\\Layer\\{acquisition_name}"

    display_name = root.find(f".//ns0:displayName[.='{folder_path}']", namespaces)
    parent = display_name.getparent()
    rotation = parent.find("ns0:rotation", namespaces).values()[-1]

    return {"angle_deg": float(rotation)}


def parse_maps_acquisition(
    project_path: str | Path,
    acquisition_name: str,
    gridmode: bool = False,
) -> TiledImage:
    """Parse MAPS acquisition and return list of tiled images."""
    acquisition_path = Path(project_path) / "LayersData" / "Layer" / acquisition_name
    if not acquisition_path.exists():
        raise FileNotFoundError(f"Acquisition not found: {acquisition_path}")

    tif_list = list(acquisition_path.glob("*.tif"))
    if len(tif_list) == 0:
        raise FileNotFoundError(f"No TIFF files found in {acquisition_path}")

    tiled_image = _build_tiled_image(
        tif_list,
        zarr_name=acquisition_name.replace(" ", "_"),
        metadata_dict=_parse_maps_metadata(project_path, acquisition_name),
        gridmode=gridmode,
    )

    return tiled_image
