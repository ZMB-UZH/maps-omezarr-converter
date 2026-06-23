# MAPS OME-Zarr Converter

A [Fractal](https://fractal-analytics-platform.github.io/) task to convert
Thermo Fisher **MAPS** acquisitions into the
[OME-Zarr](https://ngff.openmicroscopy.org/) format.

Currently supported instruments:
- TEM - FEI Talos

## Tasks

| Task | Use case |
|---|---|
| `Convert MAPS Acquisition to OME-Zarr` | Convert a MAPS acquisition (a folder of FEI/Thermo Fisher TIFF tiles) into a single stitched OME-Zarr image. |

The task is a Fractal **compound task**: an init step parses the MAPS metadata
and builds the parallelization list, and a compute step writes the image data
image-by-image.

## Installation

```bash
pip install git+https://github.com/ZMB-UZH/maps-omezarr-converter.git
```

## Python API

The converter is also available as a regular Python function, for use outside
Fractal:

```python
from maps_omezarr_converter import MapsAcquisitionModel, convert_maps_to_omezarr

convert_maps_to_omezarr(
    zarr_dir="/path/to/zarr_dir",
    acquisitions=[
        MapsAcquisitionModel(
            project_path="/path/to/maps_project",
            layer="Layer_name"
            acquisition_name="acquisition_name",
        ),
    ],
)
```