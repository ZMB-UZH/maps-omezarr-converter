"""Parse MAPS acquisition metadata into ``TiledImage`` objects.

A MAPS acquisition is a folder of single-plane TIFF tiles produced by FEI/Thermo
Fisher MAPS software. Each tile carries its stage position in an embedded
``FEI_TITAN`` XML tag; the in-plane rotation of the acquisition is read from the
project's ``MapsProject.xml``. Every tile becomes a positioned field of view
inside a single OME-Zarr image, which ``ome-zarr-converters-tools`` then tiles
and stitches according to the chosen ``ConverterOptions``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

import numpy as np
import tifffile
from lxml import etree
from ome_zarr_converters_tools import (
    AcquisitionDetails,
    ChannelInfo,
    ConverterOptions,
    SingleImage,
    Tile,
    TiledImage,
    default_axes_builder,
    tiles_aggregation_pipeline,
)

from maps_omezarr_converter.common._loaders import MapsTiffLoader

if TYPE_CHECKING:
    from pathlib import Path

    from maps_omezarr_converter.maps.convert_maps_init_task import MapsAcquisitionModel

logger = logging.getLogger(__name__)

# Namespace of the FEI/Thermo Fisher MAPS project XML.
_MAPS_PROJECT_NS = {
    "ns0": "http://schemas.datacontract.org/2004/07/Fei.Applications.Perseus.Project"
}

# Single grayscale channel for MAPS (EM) data.
_CHANNEL_LABEL = "C00"


def _parse_rotation_angle(project_path: Path, acquisition_name: str) -> float:
    """Read the acquisition's in-plane rotation angle (degrees) from the project.

    This is admittedly brittle, but it matches the MAPS project XML layout.
    Returns ``0.0`` (with a warning) if the layer entry cannot be found.
    """
    xml_path = project_path / "MapsProject.xml"
    if not xml_path.exists():
        raise FileNotFoundError(f"Project XML not found: {xml_path}")

    tree = etree.parse(str(xml_path))
    root = tree.getroot()
    folder_path = f"LayersData\\Layer\\{acquisition_name}"
    display_name = root.find(f".//ns0:displayName[.='{folder_path}']", _MAPS_PROJECT_NS)
    if display_name is None:
        logger.warning(
            f"Could not find layer '{acquisition_name}' in {xml_path}; "
            "defaulting rotation angle to 0."
        )
        return 0.0
    parent = display_name.getparent()
    rotation = parent.find("ns0:rotation", _MAPS_PROJECT_NS).values()[-1]
    return float(rotation)


def _rotation_matrix(angle_deg: float) -> np.ndarray:
    """Build the 2x2 rotation matrix applied to stage positions."""
    angle = -np.deg2rad(angle_deg)
    return np.array(
        [
            [np.cos(angle), -np.sin(angle)],
            [np.sin(angle), np.cos(angle)],
        ]
    )


def _get_stage_position(
    tif_path: Path, transform_matrix: np.ndarray
) -> tuple[float, float]:
    """Read the (rotated) stage position of a tile, in micrometers."""
    with tifffile.TiffFile(tif_path) as tif:
        root = ET.fromstring(tif.pages[0].tags["FEI_TITAN"].value)
    stage = root.find("StageSettings").find("StagePosition")
    stage_pos_x = float(stage.find("X").text) * 10**6
    stage_pos_y = float(stage.find("Y").text) * 10**6
    stage_pos_x, stage_pos_y = np.dot(
        transform_matrix, np.array([stage_pos_x, stage_pos_y])
    )
    # The image origin (as in most viewers) is in the top-left corner, so the
    # y position is inverted, which is equivalent to flipping along the y axis.
    return stage_pos_x, -stage_pos_y


def _read_tile_geometry(tif_path: Path) -> tuple[int, int, float, float]:
    """Read tile shape (pixels) and pixel size (micrometers) from a tile.

    Returns:
        (shape_x, shape_y, scale_x, scale_y)
    """
    with tifffile.TiffFile(tif_path) as tif:
        page = tif.pages[0]
        shape_x = page.tags["ImageWidth"].value
        shape_y = page.tags["ImageLength"].value
        root = ET.fromstring(page.tags["FEI_TITAN"].value)
    pixel_size = root.find("BinaryResult").find("PixelSize")
    scale_x = float(pixel_size.find("X").text) * 10**6
    scale_y = float(pixel_size.find("Y").text) * 10**6
    return shape_x, shape_y, scale_x, scale_y


def _build_tiles(acquisition_model: MapsAcquisitionModel) -> list[Tile]:
    """Build positioned ``Tile`` objects for every TIFF in the acquisition."""
    acquisition_path = acquisition_model.acquisition_path
    tif_list = sorted(acquisition_path.glob("*.tif"))
    if not tif_list:
        raise FileNotFoundError(f"No TIFF files found in {acquisition_path}")

    shape_x, shape_y, scale_x, scale_y = _read_tile_geometry(tif_list[0])
    if not np.isclose(scale_x, scale_y):
        logger.warning(
            f"Pixel size x ({scale_x}) and y ({scale_y}) differ; using x for "
            "the pixel size."
        )

    angle_deg = _parse_rotation_angle(
        acquisition_model.project_path_obj, acquisition_model.acquisition_name
    )
    transform_matrix = _rotation_matrix(angle_deg)

    acquisition_details = AcquisitionDetails(
        channels=[ChannelInfo(channel_label=_CHANNEL_LABEL)],
        pixelsize=scale_x,
        z_spacing=1.0,
        t_spacing=1.0,
        axes=default_axes_builder(is_time_series=False),
    )
    acquisition_details = acquisition_model.advanced.update_acquisition_details(
        acquisition_details
    )

    collection = SingleImage(image_path=acquisition_model.normalized_image_name)

    tiles = []
    for tif_path in tif_list:
        pos_x, pos_y = _get_stage_position(tif_path, transform_matrix)
        tiles.append(
            Tile(
                fov_name=tif_path.stem,
                start_x=pos_x,
                start_y=pos_y,
                start_z=0,
                length_x=shape_x,
                length_y=shape_y,
                length_z=1,
                length_c=1,
                length_t=1,
                collection=collection,
                image_loader=MapsTiffLoader(file_path=str(tif_path)),
                acquisition_details=acquisition_details,
                attributes={},
            )
        )
    return tiles


def parse_maps_acquisition(
    *,
    acquisition_model: MapsAcquisitionModel,
    converter_options: ConverterOptions,
) -> list[TiledImage]:
    """Parse a MAPS acquisition and return a list of tiled images.

    Args:
        acquisition_model: Acquisition input model (project path, acquisition
            name and advanced options).
        converter_options: Converter options for tile processing.

    Returns:
        List of TiledImage objects ready for conversion.
    """
    tiles = _build_tiles(acquisition_model)
    logger.info(f"Built {len(tiles)} tiles")

    return tiles_aggregation_pipeline(
        tiles=tiles,
        converter_options=converter_options,
        filters=acquisition_model.advanced.filters,
    )
