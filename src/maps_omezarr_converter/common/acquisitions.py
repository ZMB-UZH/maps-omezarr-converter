"""Acquisition input models and the shared init-task driver.

Holds the acquisition base model and the helpers that turn a list of
acquisitions into a Fractal parallelization list. Used by the
``convert_*_init_task`` entrypoints.
"""

import logging
from typing import Literal, Protocol, TypeVar

import polars
from ome_zarr_converters_tools import (
    AttributeType,
    ConverterOptions,
    OverwriteMode,
    TiledImage,
    setup_images_for_conversion,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class BaseAcquisitionModel(BaseModel):
    """Shared base for MAPS acquisition models.

    Subclasses add their format-specific fields (and an ``advanced`` field,
    declared last so it renders at the bottom of the Fractal task form).
    """


AcquisitionModelType = TypeVar(
    "AcquisitionModelType", bound=BaseAcquisitionModel, contravariant=True
)


class ParserProtocol(Protocol[AcquisitionModelType]):
    """Protocol for acquisition metadata parser."""

    def __call__(
        self,
        *,
        acquisition_model: AcquisitionModelType,
        converter_options: ConverterOptions,
    ) -> list[TiledImage]:
        """Parse the acquisition metadata and return tiled images."""
        ...


def parse_acquisitions(
    *,
    parse_function: ParserProtocol[AcquisitionModelType],
    acquisitions: list[AcquisitionModelType],
    converter_options: ConverterOptions,
) -> list[TiledImage]:
    """Parse the acquisitions metadata and return tiled images.

    Args:
        parse_function (Callable): Function to parse the acquisition metadata
            and return tiled images.
        acquisitions (list[AcquisitionModelType]): List of acquisition models.
        converter_options (ConverterOptions): Converter options.

    Returns:
        list[TiledImage]: List of tiled images.
    """
    if not acquisitions:
        raise ValueError("Acquisitions list is empty.")

    tiled_images = []
    for acq in acquisitions:
        _tiled_images = parse_function(
            acquisition_model=acq,
            converter_options=converter_options,
        )

        if not _tiled_images:
            logger.warning(f"No images found in {acq}")
            continue
        else:
            logger.info(f"Found {len(_tiled_images)} images in acquisition {acq}")
        tiled_images.extend(_tiled_images)

    if len(tiled_images) == 0:
        raise ValueError("No images found in any of the provided acquisitions.")
    logger.info(f"Total {len(tiled_images)} images found in all acquisitions.")
    return tiled_images


def run_convert_init(
    *,
    zarr_dir: str,
    acquisitions: list[AcquisitionModelType],
    parse_function: ParserProtocol[AcquisitionModelType],
    converter_options: ConverterOptions,
    overwrite: OverwriteMode,
    collection_type: Literal["SingleImage", "ImageInPlate"],
) -> dict:
    """Run an init task: parse acquisitions and build the parallelization list.

    Returns:
        dict: ``{"parallelization_list": [...]}`` for the Fractal compute task.
    """
    tiled_images = parse_acquisitions(
        parse_function=parse_function,
        acquisitions=acquisitions,
        converter_options=converter_options,
    )

    parallelization_list = setup_images_for_conversion(
        tiled_images=tiled_images,
        zarr_dir=zarr_dir,
        converter_options=converter_options,
        collection_type=collection_type,
        overwrite_mode=overwrite,
        ngff_version=converter_options.omezarr_options.ngff_version,
    )
    logger.info(
        f"Prepared parallelization list with {len(parallelization_list)} items."
    )
    return {"parallelization_list": parallelization_list}


def get_attributes_from_condition_table(
    condition_table: polars.DataFrame | None,
    row: str,
    column: int,
    acquisition: int = 0,
) -> dict[str, AttributeType]:
    """Get the attributes from the condition table."""
    if condition_table is None:
        return {}
    columns = condition_table.columns
    columns_lower = [col.lower() for col in columns]
    if "row" not in columns_lower:
        raise ValueError("Condition table must contain a 'row' column.")
    row_col_name = columns[columns_lower.index("row")]

    if "column" in columns_lower:
        column_col_name = columns[columns_lower.index("column")]
    elif "col" in columns_lower:
        column_col_name = columns[columns_lower.index("col")]
    else:
        raise ValueError("Condition table must contain a 'column' or 'col' column.")

    filtered = condition_table.filter(
        (polars.col(row_col_name) == row) & (polars.col(column_col_name) == column)
    )
    if "acquisition" in columns_lower:
        acquisition_col_name = columns[columns_lower.index("acquisition")]
        filtered = filtered.filter(polars.col(acquisition_col_name) == acquisition)
    if filtered.is_empty():
        logger.warning(
            f"No matching entry found in condition table "
            f"for row:{row} / column:{column} / acquisition:{acquisition}"
        )
        return {}
    filtered_dict = filtered.to_dict(as_series=False)
    attributes = {}
    for key, value in filtered_dict.items():
        if key in ["row", "column", "acquisition"]:
            continue
        if all(isinstance(v, str | type(None)) for v in value):
            formatted_value = [v if v is None else v.strip() for v in value]
            # Replace common placeholder values with None
            formatted_value = [
                None if v in ["", "Na", "NA", "N/A"] else v for v in formatted_value
            ]
            attributes[key] = formatted_value
        elif all(isinstance(v, int | float | bool | type(None)) for v in value):
            attributes[key] = value
        else:
            types_found = {type(v).__name__ for v in value}
            raise ValueError(
                f"Condition table column '{key}' must contain either all strings"
                f", bools, or all numbers, but found types: {types_found}"
            )

    return attributes
