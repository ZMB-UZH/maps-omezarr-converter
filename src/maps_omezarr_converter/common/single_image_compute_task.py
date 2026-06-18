"""Compute task for single-image MAPS acquisitions."""

import logging
import time

from ome_zarr_converters_tools import (
    ConvertParallelInitArgs,
    ImageListUpdateDict,
    SingleImage,
    generic_compute_task,
)
from pydantic import validate_call

from maps_omezarr_converter.common._loaders import MapsTiffLoader

logger = logging.getLogger(__name__)


@validate_call
def single_image_compute_task(
    *,
    # Fractal parameters
    zarr_url: str,
    init_args: ConvertParallelInitArgs,
) -> ImageListUpdateDict:
    """Create a single standalone OME-Zarr image from a MAPS acquisition.

    Args:
        zarr_url (str): URL to the OME-Zarr image to populate.
        init_args (ConvertParallelInitArgs): Arguments from the init task.

    Returns:
        ImageListUpdateDict: The Fractal image-list update for the new image.
    """
    timer = time.time()
    img_list_update = generic_compute_task(
        zarr_url=zarr_url,
        init_args=init_args,
        collection_type=SingleImage,
        image_loader_type=MapsTiffLoader,
    )
    zarr_output = img_list_update["image_list_updates"][0]["zarr_url"]
    run_time = time.time() - timer
    logger.info(f"Successfully converted: {zarr_output}, in {run_time:.2f}[s]")
    return img_list_update


if __name__ == "__main__":
    from fractal_task_tools.task_wrapper import run_fractal_task

    run_fractal_task(task_function=single_image_compute_task, logger_name=logger.name)
