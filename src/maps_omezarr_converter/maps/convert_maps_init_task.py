"""Initialize the MAPS acquisition to OME-Zarr conversion task."""

import logging
import re
from pathlib import Path

from ome_zarr_converters_tools import (
    AcquisitionOptions,
    ConverterOptions,
    OverwriteMode,
)
from pydantic import Field, model_validator, validate_call

from maps_omezarr_converter.common import BaseAcquisitionModel, run_convert_init
from maps_omezarr_converter.maps._parser import parse_maps_acquisition

logger = logging.getLogger("convert_maps_task")


default_converter_options = ConverterOptions()


def _is_blank(value: str | None) -> bool:
    """Return True if the value is None or only whitespace."""
    return value is None or value.strip() == ""


class MapsAcquisitionModel(BaseAcquisitionModel):
    """Model for FEI/Thermo Fisher MAPS acquisitions.

    A MAPS acquisition is identified by the project folder, the layer (folder
    under ``LayersData``) and the acquisition name (folder under the layer). All
    TIFF tiles in that acquisition are stitched into a single OME-Zarr image.

    The ``layer`` and ``acquisition_name`` fields support batch conversion:

    - Both set: convert that single acquisition.
    - ``layer`` set, ``acquisition_name`` empty: convert every acquisition in
      that layer.
    - ``layer`` empty: convert every acquisition in every layer (in which case
      ``acquisition_name`` must also be empty).
    """

    project_path: str
    """Path to the MAPS project folder (the folder containing ``MapsProject.xml``)."""

    layer: str | None = "Layer"
    """
    Name of the layer the acquisition belongs to (the folder under
    ``LayersData``). MAPS projects can have multiple, arbitrarily named layers;
    defaults to ``"Layer"``. Leave empty to convert all layers.
    """

    acquisition_name: str | None = None
    """
    Name of the acquisition to convert (the folder name under the layer). Leave
    empty to convert all acquisitions in the layer.
    """

    image_name: str | None = None
    """
    Optional custom name for the output OME-Zarr image. Only applies when
    converting a single acquisition; ignored for batch conversions. If not
    provided, the name is derived from the acquisition name.
    """

    advanced: AcquisitionOptions = Field(default_factory=AcquisitionOptions)
    """Advanced acquisition options."""

    @model_validator(mode="after")
    def _check_layer_acquisition(self) -> "MapsAcquisitionModel":
        """Disallow selecting an acquisition without a layer."""
        if self.layer_is_empty and not self.acquisition_is_empty:
            raise ValueError(
                "When 'layer' is empty (convert all layers), 'acquisition_name' "
                "must also be empty."
            )
        return self

    @property
    def layer_is_empty(self) -> bool:
        """Whether the layer is unset (convert all layers)."""
        return _is_blank(self.layer)

    @property
    def acquisition_is_empty(self) -> bool:
        """Whether the acquisition name is unset (convert all in the layer)."""
        return _is_blank(self.acquisition_name)

    @property
    def is_single_acquisition(self) -> bool:
        """Whether exactly one acquisition is selected by name."""
        return not self.layer_is_empty and not self.acquisition_is_empty

    @property
    def project_path_obj(self) -> Path:
        """The project path as a ``Path``."""
        return Path(self.project_path)

    @property
    def acquisition_path(self) -> Path:
        """Path to the acquisition directory containing the TIFF tiles.

        Only meaningful when a single acquisition is selected.
        """
        return self.project_path_obj / "LayersData" / self.layer / self.acquisition_name

    @property
    def display_name_path(self) -> str:
        """The acquisition's ``displayName`` key in ``MapsProject.xml``.

        Only meaningful when a single acquisition is selected.
        """
        return f"LayersData\\{self.layer}\\{self.acquisition_name}"

    @property
    def normalized_image_name(self) -> str:
        """Get the sanitized output image name (single-acquisition case)."""
        name = self.image_name if self.image_name is not None else self.acquisition_name
        return re.sub(r"[^A-Za-z0-9\-_. ]", "_", name or "")


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
