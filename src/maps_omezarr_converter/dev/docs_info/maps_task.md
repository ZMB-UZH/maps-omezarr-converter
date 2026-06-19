### Purpose
- Convert a FEI/Thermo Fisher MAPS acquisition to a single stitched OME-Zarr image.

### Outputs
- One OME-Zarr image per acquisition.

### Limitations
- This task has been tested on a limited set of MAPS acquisitions. It may not work on all MAPS projects.
- Tile positions are reconstructed from the grid geometry in `MapsProject.xml` (columns, rows, tile and mosaic field widths, pixel size) combined with each tile's `(row, column)` index from its filename. This works regardless of whether the tiles embed the `FEI_TITAN` metadata tag.
- The output mosaic is axis-aligned (the project's in-plane rotation is not applied).
- Only tile-scan acquisitions are supported. MAPS-generated "Stitched images" layers (pre-stitched pyramids) are **not** converted — convert the underlying raw tile-scan acquisition instead.
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
- `Layer`: the `{layer}` folder under `LayersData`. MAPS projects can have multiple, arbitrarily named layers; defaults to `Layer`. Leave empty to convert **all** layers.
- `Acquisition Name`: the `{acquisition_name}` folder under the layer. Leave empty to convert **all** acquisitions in the layer.
- output: one OME-Zarr image per acquisition, stitched from its TIFF tiles.

Batch conversion (one acquisition entry can expand to many images):

- `Layer` + `Acquisition Name` set: convert that single acquisition.
- `Layer` set, `Acquisition Name` empty: convert every acquisition in that layer.
- `Layer` empty: convert every acquisition in every layer (`Acquisition Name` must also be empty).

Output naming: in projects that contain more than one layer, the layer name is prefixed to each output image name (e.g. `cell1_1.7 nm`) for provenance and to avoid collisions; single-layer projects use the acquisition name alone. An explicit `Image Name` (single-acquisition conversions only) overrides this.
