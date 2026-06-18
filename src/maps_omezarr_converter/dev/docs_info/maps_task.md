### Purpose
- Convert a FEI/Thermo Fisher MAPS acquisition to a single stitched OME-Zarr image.

### Outputs
- One OME-Zarr image per acquisition.

### Limitations
- This task has been tested on a limited set of MAPS acquisitions. It may not work on all MAPS projects.
- Tile stage positions and pixel size are read from the embedded `FEI_TITAN` TIFF tag; the in-plane rotation angle is read from `MapsProject.xml`.
- See below for more detailed input expectations.

### Expected inputs
The acquisition is identified by the MAPS **project folder** and the **acquisition name** (the layer folder name). (The names in curly braces `{}` can be freely chosen by the user.)

```text
.../{project}
----/MapsProject.xml
----/LayersData
--------/Layer
------------/{acquisition_name}
----------------/{tile1}.tif
----------------/{tile2}.tif
----------------/...
```

- `Project Path`: path to `.../{project}` (the folder containing `MapsProject.xml`).
- `Acquisition Name`: the `{acquisition_name}` folder under `LayersData/Layer`.
- output: a single OME-Zarr image stitched from all TIFF tiles in the acquisition.
