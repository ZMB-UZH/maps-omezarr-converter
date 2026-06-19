"""Python API for the MAPS converter."""

from ome_zarr_converters_tools import (
    ConverterOptions,
    OverwriteMode,
    RunnerType,
    exec_compound_task,
)
from ome_zarr_converters_tools.fractal import ImageListUpdateDict

from maps_omezarr_converter.common import single_image_compute_task
from maps_omezarr_converter.maps.convert_maps_init_task import (
    MapsAcquisitionModel,
    convert_maps_init_task,
)


def convert_maps_to_omezarr(
    *,
    zarr_dir: str,
    acquisitions: list[MapsAcquisitionModel],
    converter_options: ConverterOptions | None = None,
    overwrite: OverwriteMode = OverwriteMode.NO_OVERWRITE,
    runner: RunnerType | None = None,
) -> list[ImageListUpdateDict]:
    """Convert MAPS acquisitions to OME-Zarr.

    Each acquisition (a folder of MAPS TIFF tiles) is stitched into a single
    standalone OME-Zarr image.

    Args:
        zarr_dir (str): Directory to store the Zarr files.
        acquisitions (list[MapsAcquisitionModel]): List of MAPS acquisitions to
            convert to OME-Zarr.
        converter_options (ConverterOptions | None): Advanced converter options.
        overwrite (OverwriteMode): Overwrite mode for existing data.
            - "No Overwrite": Do not overwrite existing data.
            - "Overwrite": Remove and replace existing data.
            - "Extend": Extend existing data without removing it.
            Default is "No Overwrite".
        runner (RunnerType | None): Execution strategy for compute tasks.
            Use SequentialRunner (default), ThreadedRunner, or MultiprocessingRunner.

    Returns:
        list[ImageListUpdateDict]: List of image list update dicts for the converted
            Zarr images.
    """
    converter_options = converter_options or ConverterOptions()
    init_task_kwargs = {
        "zarr_dir": zarr_dir,
        "acquisitions": acquisitions,
        "converter_options": converter_options,
        "overwrite": overwrite,
    }
    return exec_compound_task(
        init_task_fn=convert_maps_init_task,
        compute_task_fn=single_image_compute_task,
        init_task_kwargs=init_task_kwargs,
        runner=runner,
    )
