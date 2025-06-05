"""MAPS to OME-Zarr conversion task initialization."""

import logging
from pathlib import Path

from fractal_converters_tools import (
    AdvancedComputeOptions,
    build_parallelization_list,
)
from pydantic import BaseModel, validate_call

from maps_omezarr_converter.maps_utils import parse_maps_acquisition

logger = logging.getLogger(__name__)


class mapsInputModel(BaseModel):
    """Acquisition metadata.

    Attributes:
        project_path (str): Path to the MAPS project folder.
        acquisition_name: (str): Name of the acquisition to convert. (Folder
            name in LayersData/Layer)
    """

    project_path: str
    acquisition_name: str


@validate_call
def convert_maps_init_task(
    *,
    # Fractal parameters
    zarr_dir: str,
    # Task parameters
    acquisitions: list[mapsInputModel],
    overwrite: bool = False,
    advanced_options: AdvancedComputeOptions = AdvancedComputeOptions(),  # noqa: B008
):
    """Initialize the MAPS to OME-Zarr conversion task.

    Args:
        zarr_dir (str): Directory to store the Zarr files.
        acquisitions (list[AcquisitionInputModel]): List of raw acquisitions to convert
            to OME-Zarr.
        overwrite (bool): Overwrite existing Zarr files.
        advanced_options (AdvancedComputeOptions): Advanced options for the conversion.
    """
    if not acquisitions:
        raise ValueError("No acquisitions provided.")

    zarr_dir_path = Path(zarr_dir)

    if not zarr_dir_path.exists():
        logger.info(f"Creating directory: {zarr_dir_path}")
        zarr_dir_path.mkdir(parents=True)

    if advanced_options.tiling_mode in ["auto", "grid"]:
        gridmode = True
    else:
        gridmode = False

    # prepare the parallel list of zarr urls
    tiled_images = []
    for acq in acquisitions:
        _tiled_image = parse_maps_acquisition(
            project_path=Path(acq.project_path),
            acquisition_name=acq.acquisition_name,
            gridmode=gridmode,
        )
        tiled_images.append(_tiled_image)

    # Common fractal-converters-tools functions
    parallelization_list = build_parallelization_list(
        zarr_dir=zarr_dir_path,
        tiled_images=tiled_images,
        overwrite=overwrite,
        advanced_compute_options=advanced_options,
    )
    logger.info(f"Total {len(parallelization_list)} images to convert.")

    return {"parallelization_list": parallelization_list}


if __name__ == "__main__":
    from fractal_task_tools.task_wrapper import run_fractal_task

    run_fractal_task(task_function=convert_maps_init_task, logger_name=logger.name)
