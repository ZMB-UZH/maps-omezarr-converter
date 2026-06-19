"""Parse MAPS acquisition metadata into ``TiledImage`` objects.

A MAPS acquisition is a folder of single-plane TIFF tiles produced by FEI/Thermo
Fisher MAPS software, laid out on a regular grid. Tile positions are
reconstructed from the **grid geometry** stored in the project's
``MapsProject.xml`` (number of columns/rows, tile and mosaic field widths, pixel
size) combined with each tile's ``(row, column)`` index encoded in its filename
(``Tile_{row}-{col}-...``).

The project XML also enumerates every acquisition (by its ``displayName``), so a
single acquisition model can expand to a batch: one acquisition, all
acquisitions in a layer, or all acquisitions in every layer (see
``_resolve_acquisitions``). Each acquisition becomes its own single OME-Zarr
image, which ``ome-zarr-converters-tools`` then tiles and stitches according to
the chosen ``ConverterOptions``.

This grid-based approach works for every MAPS export, including those whose tiles
do not embed the ``FEI_TITAN`` metadata tag, and was validated to reproduce the
per-tile stage positions of tag-bearing exports to ~0.01 px on the lattice.
"""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING, NamedTuple

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


class _GridGeometry(NamedTuple):
    """Grid geometry of one acquisition, read from ``MapsProject.xml``."""

    columns: int
    rows: int
    tile_hfw_um: float  # full width of a single tile, micrometers
    total_hfw_um: float  # full width of the whole mosaic, micrometers
    total_vfw_um: float | None  # full height of the mosaic (if present), um
    pixel_um: float  # micrometers per pixel


def _sanitize_name(name: str) -> str:
    """Sanitize a name for use as an OME-Zarr image path."""
    return re.sub(r"[^A-Za-z0-9\-_. ]", "_", name)


def _load_project_root(project_path: Path):
    """Parse ``MapsProject.xml`` and return its root element."""
    xml_path = project_path / "MapsProject.xml"
    if not xml_path.exists():
        raise FileNotFoundError(f"Project XML not found: {xml_path}")
    return etree.parse(str(xml_path)).getroot()


def _iter_project_acquisitions(root) -> list[tuple[str, str, str]]:
    """List the real tile acquisitions declared in the project.

    Returns a list of ``(layer, acquisition_name, display_name_path)`` tuples.
    Real tile acquisitions have both ``columns`` and ``rows``; derived layers
    (stitched images, line scans, ...) do not, and are excluded.
    """
    acquisitions = []
    for display_name in root.findall(".//ns0:displayName", _MAPS_PROJECT_NS):
        text = display_name.text
        if not text or "LayersData" not in text:
            continue
        parent = display_name.getparent()
        has_grid = (
            parent.find("ns0:columns", _MAPS_PROJECT_NS) is not None
            and parent.find("ns0:rows", _MAPS_PROJECT_NS) is not None
        )
        if not has_grid:
            continue
        parts = text.split("\\")
        if len(parts) < 3:
            continue
        layer = parts[1]
        acquisition_name = "\\".join(parts[2:])
        acquisitions.append((layer, acquisition_name, text))
    return acquisitions


def _list_acquisition_paths(root) -> list[str]:
    """List the ``displayName`` paths of real tile acquisitions in the project."""
    return [path for _, _, path in _iter_project_acquisitions(root)]


def _find_acquisition_node(root, display_name_path: str):
    """Find the layer node for an acquisition by its ``displayName`` key.

    Matches case-insensitively: the XML may store the layer name with a different
    case than the on-disk folder (e.g. XML "cell1" vs disk "Cell1").
    """
    target = display_name_path.lower()
    for display_name in root.findall(".//ns0:displayName", _MAPS_PROJECT_NS):
        if display_name.text and display_name.text.lower() == target:
            return display_name.getparent()
    return None


def _grid_geometry_from_node(node, display_name_path: str) -> _GridGeometry:
    """Read grid geometry from an acquisition's XML node.

    Reads ``columns``, ``rows``, ``tileHfw``, ``totalHfw`` (and ``totalVfw`` if
    present) and ``pixelSize``. Lengths are converted from meters to micrometers.
    """

    def _value(field: str) -> float | None:
        """Read a field as float, from the ``Value`` attribute or element text."""
        el = node.find(f"ns0:{field}", _MAPS_PROJECT_NS)
        if el is None:
            return None
        raw = el.get("Value")
        if raw is None:
            raw = el.text
        if raw is None or raw == "":
            return None
        return float(raw)

    columns = _value("columns")
    rows = _value("rows")
    tile_hfw = _value("tileHfw")
    total_hfw = _value("totalHfw")
    total_vfw = _value("totalVfw")
    pixel = _value("pixelSize")

    missing = [
        name
        for name, value in (
            ("columns", columns),
            ("rows", rows),
            ("tileHfw", tile_hfw),
            ("totalHfw", total_hfw),
            ("pixelSize", pixel),
        )
        if value is None
    ]
    if missing:
        raise ValueError(
            f"Missing grid geometry fields {missing} for '{display_name_path}'."
        )

    return _GridGeometry(
        columns=int(columns),
        rows=int(rows),
        tile_hfw_um=tile_hfw * 1e6,
        total_hfw_um=total_hfw * 1e6,
        total_vfw_um=(total_vfw * 1e6 if total_vfw is not None else None),
        pixel_um=pixel * 1e6,
    )


def _read_grid_geometry(project_path: Path, display_name_path: str) -> _GridGeometry:
    r"""Read an acquisition's grid geometry from ``MapsProject.xml``.

    Looks up the acquisition by its ``displayName`` key
    (``LayersData\{layer}\{acquisition_name}``) and reads its grid geometry.
    """
    root = _load_project_root(project_path)
    node = _find_acquisition_node(root, display_name_path)
    if node is None:
        available = _list_acquisition_paths(root)
        raise ValueError(
            f"Acquisition '{display_name_path}' not found in MapsProject.xml. "
            f"Available acquisitions: {available}"
        )
    return _grid_geometry_from_node(node, display_name_path)


def _grid_step_um(geom: _GridGeometry) -> float:
    """Compute the spacing between adjacent tile origins, in micrometers.

    With ``columns`` tiles each ``tile_hfw`` wide, evenly spaced by ``step``, the
    mosaic width is ``tile_hfw + (columns - 1) * step``; solving for ``step``
    gives the spacing. The same step applies to both axes (square tiles, isotropic
    pixels, symmetric overlap). For single-column grids the vertical ``totalVfw``
    is used instead when available.
    """
    if geom.columns > 1:
        return (geom.total_hfw_um - geom.tile_hfw_um) / (geom.columns - 1)
    if geom.rows > 1 and geom.total_vfw_um is not None:
        return (geom.total_vfw_um - geom.tile_hfw_um) / (geom.rows - 1)
    if geom.rows > 1:
        raise ValueError(
            "Cannot determine tile spacing for a single-column acquisition "
            "without a 'totalVfw' entry in MapsProject.xml."
        )
    return 0.0  # single tile


def _parse_tile_row_col(tif_path: Path) -> tuple[int, int]:
    """Parse the 1-based ``(row, column)`` grid index from a tile filename.

    Filenames look like ``Tile_{row}-{col}-000000_0-000.tif``.
    """
    try:
        row_str, col_str = tif_path.stem.split("_")[1].split("-")[:2]
        return int(row_str), int(col_str)
    except (IndexError, ValueError) as exc:
        raise ValueError(
            f"Cannot parse row/column from tile filename: {tif_path.name}"
        ) from exc


def _read_tile_pixel_dims(tif_path: Path) -> tuple[int, int]:
    """Read a tile's pixel dimensions ``(width, height)`` from the TIFF."""
    with tifffile.TiffFile(tif_path) as tif:
        page = tif.pages[0]
        return page.imagewidth, page.imagelength


def _resolve_child_dir(parent: Path, name: str) -> Path | None:
    """Resolve a child directory by name, case-insensitively.

    Handles the case mismatch between the XML layer name and the on-disk folder
    (e.g. XML "cell1" vs disk "Cell1").
    """
    candidate = parent / name
    if candidate.is_dir():
        return candidate
    if not parent.is_dir():
        return None
    lower = name.lower()
    for child in parent.iterdir():
        if child.is_dir() and child.name.lower() == lower:
            return child
    return None


def _resolve_acquisitions(
    acquisition_model: MapsAcquisitionModel,
    all_acquisitions: list[tuple[str, str, str]],
) -> list[tuple[str, str]]:
    """Resolve which ``(layer, acquisition_name)`` pairs to convert.

    - Single acquisition (layer and name set): that one pair, case-canonicalized
      against the project XML when possible (so single and batch conversions
      produce the same output name for the same acquisition).
    - Layer set, name empty: every acquisition in that layer.
    - Layer empty: every acquisition in every layer.
    """
    if acquisition_model.is_single_acquisition:
        layer_lower = acquisition_model.layer.lower()
        name_lower = acquisition_model.acquisition_name.lower()
        for layer, name, _ in all_acquisitions:
            if layer.lower() == layer_lower and name.lower() == name_lower:
                return [(layer, name)]
        # Not listed in the XML; fall back (the build step raises a clear error).
        return [(acquisition_model.layer, acquisition_model.acquisition_name)]

    if not acquisition_model.layer_is_empty:
        layer_lower = acquisition_model.layer.lower()
        selected = [
            (layer, name)
            for layer, name, _ in all_acquisitions
            if layer.lower() == layer_lower
        ]
        if not selected:
            layers = sorted({layer for layer, _, _ in all_acquisitions})
            raise ValueError(
                f"No acquisitions found for layer '{acquisition_model.layer}'. "
                f"Available layers: {layers}"
            )
        return selected

    selected = [(layer, name) for layer, name, _ in all_acquisitions]
    if not selected:
        raise ValueError("No tile acquisitions found in the project.")
    return selected


def _assign_image_names(
    acquisition_model: MapsAcquisitionModel,
    resolved: list[tuple[str, str]],
    multi_layer: bool,
) -> dict[tuple[str, str], str]:
    """Assign a unique output image name to each resolved acquisition.

    An explicit ``image_name`` override is honored only for a single acquisition.
    Otherwise the name is derived from the acquisition name, prefixed with the
    layer when the project contains more than one layer (``multi_layer``) — so
    images from multi-layer projects carry their provenance and never collide
    across layers, while single-layer projects keep clean, unprefixed names. A
    final collision check forces the layer prefix as a safety net.
    """
    if (
        acquisition_model.is_single_acquisition
        and acquisition_model.image_name is not None
    ):
        layer, name = resolved[0]
        return {(layer, name): acquisition_model.normalized_image_name}

    if multi_layer:
        names = {
            (layer, name): _sanitize_name(f"{layer}_{name}")
            for layer, name in resolved
        }
    else:
        names = {(layer, name): _sanitize_name(name) for layer, name in resolved}

    if len(set(names.values())) != len(names):
        names = {
            (layer, name): _sanitize_name(f"{layer}_{name}")
            for layer, name in resolved
        }
    return names


def _build_acquisition_tiles(
    project_path: Path,
    root,
    layer: str,
    acquisition_name: str,
    image_name: str,
    advanced,
) -> list[Tile]:
    """Build positioned ``Tile`` objects for a single acquisition."""
    layers_dir = project_path / "LayersData"
    layer_dir = _resolve_child_dir(layers_dir, layer)
    acquisition_dir = (
        _resolve_child_dir(layer_dir, acquisition_name) if layer_dir else None
    )
    if acquisition_dir is None:
        raise FileNotFoundError(
            f"Acquisition directory not found: "
            f"{layers_dir / layer / acquisition_name}"
        )
    tif_list = sorted(acquisition_dir.glob("*.tif"))
    if not tif_list:
        raise FileNotFoundError(f"No TIFF files found in {acquisition_dir}")

    display_name_path = f"LayersData\\{layer}\\{acquisition_name}"
    node = _find_acquisition_node(root, display_name_path)
    if node is None:
        available = _list_acquisition_paths(root)
        raise ValueError(
            f"Acquisition '{display_name_path}' not found in MapsProject.xml. "
            f"Available acquisitions: {available}"
        )
    geom = _grid_geometry_from_node(node, display_name_path)
    step_um = _grid_step_um(geom)

    # All tiles in a MAPS acquisition share the same pixel dimensions; read once.
    length_x, length_y = _read_tile_pixel_dims(tif_list[0])
    expected_hfw_um = length_x * geom.pixel_um
    if not math.isclose(expected_hfw_um, geom.tile_hfw_um, rel_tol=0.02):
        logger.warning(
            f"Tile width from pixels ({expected_hfw_um:.3f} um) differs from the "
            f"project's tileHfw ({geom.tile_hfw_um:.3f} um) for '{display_name_path}'."
        )

    acquisition_details = AcquisitionDetails(
        channels=[ChannelInfo(channel_label=_CHANNEL_LABEL)],
        pixelsize=geom.pixel_um,
        z_spacing=1.0,
        t_spacing=1.0,
        axes=default_axes_builder(is_time_series=False),
    )
    acquisition_details = advanced.update_acquisition_details(acquisition_details)

    collection = SingleImage(image_path=image_name)

    tiles = []
    for tif_path in tif_list:
        row, col = _parse_tile_row_col(tif_path)
        tiles.append(
            Tile(
                fov_name=tif_path.stem,
                # Axis-aligned grid: origin anchored at row 1 / column 1.
                start_x=(col - 1) * step_um,
                start_y=(row - 1) * step_um,
                start_z=0,
                length_x=length_x,
                length_y=length_y,
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


def _build_tiles(acquisition_model: MapsAcquisitionModel) -> list[Tile]:
    """Build ``Tile`` objects for every acquisition selected by the model.

    Depending on the model, this is one acquisition, all acquisitions in a layer,
    or all acquisitions in the project. In batch mode, acquisitions that cannot
    be built (missing folder/geometry) are skipped with a warning; in
    single-acquisition mode the error is raised.
    """
    project_path = acquisition_model.project_path_obj
    root = _load_project_root(project_path)
    all_acquisitions = _iter_project_acquisitions(root)
    resolved = _resolve_acquisitions(acquisition_model, all_acquisitions)
    n_layers = len({layer for layer, _, _ in all_acquisitions})
    names = _assign_image_names(acquisition_model, resolved, multi_layer=n_layers > 1)
    logger.info(
        f"Resolved {len(resolved)} acquisition(s) to convert "
        f"(project has {n_layers} layer(s))."
    )

    tiles: list[Tile] = []
    for layer, acquisition_name in resolved:
        try:
            tiles.extend(
                _build_acquisition_tiles(
                    project_path=project_path,
                    root=root,
                    layer=layer,
                    acquisition_name=acquisition_name,
                    image_name=names[(layer, acquisition_name)],
                    advanced=acquisition_model.advanced,
                )
            )
        except (FileNotFoundError, ValueError):
            if acquisition_model.is_single_acquisition:
                raise
            logger.warning(
                f"Skipping acquisition 'LayersData\\{layer}\\{acquisition_name}'.",
                exc_info=True,
            )
    return tiles


def parse_maps_acquisition(
    *,
    acquisition_model: MapsAcquisitionModel,
    converter_options: ConverterOptions,
) -> list[TiledImage]:
    """Parse a MAPS acquisition model and return a list of tiled images.

    The model may select a single acquisition, all acquisitions in a layer, or
    all acquisitions in the project; each selected acquisition yields one
    TiledImage.

    Args:
        acquisition_model: Acquisition input model (project path, layer,
            acquisition name and advanced options).
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
