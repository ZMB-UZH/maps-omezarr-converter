### Purpose
- Convert a FEI/Thermo Fisher MAPS acquisition to a single stitched OME-Zarr image.

### Outputs
- One OME-Zarr image per acquisition.

### Limitations
- This task has been tested on a limited set of MAPS acquisitions. It may not work on all MAPS projects.
- Tile positions are reconstructed from the grid geometry in `MapsProject.xml` (columns, rows, tile and mosaic field widths, pixel size) combined with each tile's `(row, column)` index from its filename. This works regardless of whether the tiles embed the `FEI_TITAN` metadata tag.
- The output mosaic is axis-aligned (the project's in-plane rotation is not applied).
- See below for more detailed input expectations.

### Expected inputs
The acquisition is identified by the MAPS **project folder**, the **layer** name and the **acquisition name**. (The names in curly braces `{}` can be freely chosen by the user.)

```text
.../{project}
----/MapsProject.xml
----/LayersData
--------/{layer}
------------/{acquisition_name}
----------------/Tile_001-001-000000_0-000.tif
----------------/Tile_001-002-000000_0-000.tif
----------------/...
```

- `Project Path`: path to `.../{project}` (the folder containing `MapsProject.xml`).
- `Layer`: the `{layer}` folder under `LayersData`. MAPS projects can have multiple, arbitrarily named layers; defaults to `Layer`.
- `Acquisition Name`: the `{acquisition_name}` folder under the layer.
- output: a single OME-Zarr image stitched from all TIFF tiles in the acquisition.
