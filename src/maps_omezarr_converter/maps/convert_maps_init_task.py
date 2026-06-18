"""Initialize the MAPS acquisition to OME-Zarr conversion task."""

import logging
import re
from pathlib import Path

from ome_zarr_converters_tools import (
    AcquisitionOptions,
    ConverterOptions,
    OverwriteMode,
)
from pydantic import Field, validate_call

from maps_omezarr_converter.common import BaseAcquisitionModel, run_convert_init
from maps_omezarr_converter.maps._parser import parse_maps_acquisition

logger = logging.getLogger("convert_maps_task")


default_converter_options = ConverterOptions()


class MapsAcquisitionModel(BaseAcquisitionModel):
    """Model for FEI/Thermo Fisher MAPS acquisitions.

    A MAPS acquisition is identified by the project folder and the name of the
    acquisition layer (the folder name under ``LayersData/Layer``). All TIFF
    tiles in that layer are stitched into a single OME-Zarr image.
    """

    project_path: str
    """Path to the MAPS project folder (the folder containing ``MapsProject.xml``)."""

    acquisition_name: str
    """
    Name of the acquisition to convert (the folder name under
    ``LayersData/{layer}``).
    """

    layer: str = "Layer"
    """
    Name of the layer the acquisition belongs to (the folder under
    ``LayersData``). MAPS projects can have multiple, arbitrarily named layers;
    defaults to ``"Layer"``.
    """

    image_name: str | None = None
    """
    Optional custom name for the output OME-Zarr image. If not provided, the
    name is derived from the acquisition name.
    """

    advanced: AcquisitionOptions = Field(default_factory=AcquisitionOptions)
    """Advanced acquisition options."""

    @property
    def project_path_obj(self) -> Path:
        """The project path as a ``Path``."""
        return Path(self.project_path)

    @property
    def acquisition_path(self) -> Path:
        """Path to the acquisition layer directory containing the TIFF tiles."""
        return self.project_path_obj / "LayersData" / self.layer / self.acquisition_name

    @property
    def display_name_path(self) -> str:
        """The acquisition's ``displayName`` key in ``MapsProject.xml``."""
        return f"LayersData\\{self.layer}\\{self.acquisition_name}"

    @property
    def normalized_image_name(self) -> str:
        """Get the sanitized output image name."""
        name = self.image_name if self.image_name is not None else self.acquisition_name
        return re.sub(r"[^A-Za-z0-9\-_. ]", "_", name)


@validate_call
def convert_maps_init_task(
    *,
    # Fractal parameters
    zarr_dir: str,
    # Task parameters
    acquisitions: list[MapsAcquisitionModel],
    converter_options: ConverterOptions = default_converter_options,
    overwrite: OverwriteMode = OverwriteMode.NO_OVERWRITE,
):
    """Initialize the task to convert MAPS acquisitions to OME-Zarr.

    Args:
        zarr_dir (str): Directory to store the Zarr files.
        acquisitions (list[MapsAcquisitionModel]): List of MAPS acquisitions to
            convert to OME-Zarr.
        converter_options (ConverterOptions): Advanced converter options.
        overwrite (OverwriteMode): Overwrite mode for existing data.
            - "No Overwrite": Do not overwrite existing data.
            - "Overwrite": Remove and replace existing data.
            - "Extend": Extend existing data without removing it.
            Default is "No Overwrite".

    Returns:
        dict: ``{"parallelization_list": [...]}`` for the compute task.
    """
    return run_convert_init(
        zarr_dir=zarr_dir,
        acquisitions=acquisitions,
        parse_function=parse_maps_acquisition,
        converter_options=converter_options,
        overwrite=overwrite,
        collection_type="SingleImage",
    )


if __name__ == "__main__":
    from fractal_task_tools.task_wrapper import run_fractal_task

    run_fractal_task(
        task_function=convert_maps_init_task,
        logger_name=logger.name,
    )
