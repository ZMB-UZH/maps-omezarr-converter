"""MAPS to OME-Zarr conversion task compute."""

import logging
import time

from fractal_converters_tools import ConvertParallelInitArgs, generic_compute_task
from pydantic import validate_call

logger = logging.getLogger(__name__)


@validate_call
def convert_maps_compute_task(
    *,
    # Fractal parameters
    zarr_url: str,
    init_args: ConvertParallelInitArgs,
):
    """Compute task to convert a maps acquisition to OME-Zarr.

    Args:
        zarr_url (str): URL to the OME-Zarr file.
        init_args (ConvertScanrInitArgs): Arguments for the initialization task.
    """
    timer = time.time()
    img_list_update = generic_compute_task(
        zarr_url=zarr_url,
        init_args=init_args,
    )
    zarr_output = img_list_update["image_list_updates"][0]["zarr_url"]
    run_time = time.time() - timer
    logger.info(f"Succesfully converted: {zarr_output}, in {run_time:.2f}[s]")
    return img_list_update


if __name__ == "__main__":
    from fractal_task_tools.task_wrapper import run_fractal_task

    run_fractal_task(task_function=convert_maps_compute_task, logger_name=logger.name)