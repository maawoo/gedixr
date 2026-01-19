# Default Variables

In addition to shot number, acquisition time, and geolocation information, the 
following variables are extracted by default if no custom variables are provided via 
the `variables` parameter (see "Custom Variables" section below).

## GEDI L2A

**Product:** GEDI Level 2A (Geolocated Elevation and Height Metrics)

| Variable | Description | GEDI Layer Name |
|----------|-------------|-----------------|
| `rh98` | Relative height metrics at 98% interval | `rh98` |

## GEDI L2B

**Product:** GEDI Level 2B (Canopy Cover and Vertical Profile Metrics)

| Variable | Description | GEDI Layer Name |
|----------|-------------|-----------------|
| `rh100` | Height above ground of received waveform signal start | `rh100` |
| `tcc` | Total canopy cover | `cover` |
| `fhd` | Foliage Height Diversity | `fhd_normal` |
| `pai` | Total Plant Area Index | `pai` |

## Additional Base Variables (Always Included)

| Variable | Description | GEDI Layer Name |
|----------|-------------|-----------------|
| `shot` | Shot number (unique identifier) | `shot_number` |
| `acq_time` | Acquisition time | Derived from filename |
| `latitude` | Latitude of lowest mode | `lat_lowestmode` |
| `longitude` | Longitude of lowest mode | `lon_lowestmode` |
| `elev` | Elevation of lowest mode | `elev_lowestmode` |
| `elev_dem_tdx` | Digital elevation model (TanDEM-X) | `digital_elevation_model` |
| `sensitivity` | Beam sensitivity | `sensitivity` |
| `num_detectedmodes` | Number of detected modes | `num_detectedmodes` |

## Further Information

For comprehensive overviews of all available layers in each product:

- [GEDI L2A Product Information](https://lpdaac.usgs.gov/products/gedi02_av002#variables)
- [GEDI L2B Product Information](https://lpdaac.usgs.gov/products/gedi02_bv002#variables)

## Custom Variables

You can specify custom variables to extract using the `variables` parameter when calling
the `extract_data` function, or via the `--variables` option in the CLI.

The `variables` parameter accepts a list of tuples, where each tuple contains the 
desired variable name and the corresponding, exact (!) GEDI layer name after the beam 
prefix.

=== "CLI"

    ```bash
    # Extract custom variables using column_name=layer_name pairs
    gedixr extract /path/to/data --product L2A \
      --variables "rh50=rh50,rh75=rh75,solar_azimuth=solar_azimuth,treecover=land_cover_data/landsat_treecover"
    ```

=== "Python"

    ```python
    from gedixr.extract import extract_data

    variables = [
        ('rh50', 'rh50'),
        ('rh75', 'rh75'),
        ('solar_azimuth', 'solar_azimuth'),
        ('treecover', 'land_cover_data/landsat_treecover')
    ]
    gdf, out_path = extract_data(
        directory="/path/to/data",
        gedi_product='L2A',
        variables=variables
    )
    ```

This will extract the `rh50`, `rh75`, `solar_azimuth`, and `landsat_treecover` variables
in addition to the default base variables. As you can see, for nested variables (like
`landsat_treecover`), you need to provide the full path within the HDF5 structure after
the beam prefix (e.g., `BEAM0001/land_cover_data/landsat_treecover` as it appears in 
the overview linked above). In the example, the `landsat_treecover` variable will appear
in the output GeoDataFrame with the column name `treecover`.

!!! warning "Limitations"
    GEDI L2A and L2B products contain a looot of variables. Not all of them can be 
    directly extracted like this. Particularly, variables that are stored as arrays 
    (e.g., waveform data) are not supported for extraction via the `variables` parameter 
    at this time. Contributions are welcome! 😊
