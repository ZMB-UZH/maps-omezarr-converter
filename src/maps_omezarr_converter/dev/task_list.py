"""Contains the list of tasks available to fractal."""

from fractal_task_tools.task_models import ConverterCompoundTask

AUTHORS = "Flurin Sturzenegger"

TASK_LIST = [
    ConverterCompoundTask(
        name="Convert MAPS Acquisition to OME-Zarr",
        executable_init="maps/convert_maps_init_task.py",
        executable="common/single_image_compute_task.py",
        meta_init={"cpus_per_task": 1, "mem": 4000},
        meta={"cpus_per_task": 1, "mem": 12000},
        category="Conversion",
        modality="Other",
        tags=[
            "FEI",
            "Thermo Fisher",
            "MAPS",
            "EM",
            "Image converter",
        ],
        docs_info="file:docs_info/maps_task.md",
    ),
]
