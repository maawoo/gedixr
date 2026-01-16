# gedixr

Extract the variables you need from [GEDI L2A/L2B](https://gedi.umd.edu/) HDF5 files 
and start working with them as a `geopandas.GeoDataFrame` or `xarray.Dataset` in 
no time!

## Features

- **Download GEDI data** directly from NASA's Earthdata servers using Harmony API
- **Command-line interface** for quick extraction from a directory of HDF5 files
- **Logging** to monitor extraction progress and issues
- **Quality filtering** built-in with the option to skip and apply custom filters later
- **Spatial subsetting** using common vector file formats (GeoJSON, GeoPackage, etc.)
- **GeoParquet output** for efficient storage and processing

## Quick Example

=== "CLI"

    ```bash
    # Extract default L2B variables
    gedixr extract /path/to/gedi/data --product L2B
    
    # Extract default L2A variables with spatial subset
    gedixr extract /path/to/gedi/data -p L2A -v my_area.geojson
    ```

=== "Python"

    ```python
    from gedixr.gedi import extract_data
    
    # Extract default L2B variables
    gdf_l2b, out_path_l2b = extract_data(directory="path/to/data", gedi_product='L2B')

    # Extract default L2A variables with spatial subset
    gdf_l2a, out_path_l2a = extract_data(
        directory="path/to/data",
        gedi_product='L2A',
        subset_vector="my_area.geojson"
    )
    ```

## Getting Started

- [Installation Guide](installation.md) - Set up gedixr on your system
- [Quick Start](quickstart.md) - Get up and running in minutes
- [CLI Reference](cli.md) - Command-line interface documentation
- [Python API](api.md) - Python API reference

## About GEDI

The Global Ecosystem Dynamics Investigation (GEDI) is a NASA mission that provides 
high-resolution laser ranging observations of the 3D structure of the Earth's forests 
and topography. Learn more at [gedi.umd.edu](https://gedi.umd.edu/).

## License

This project is licensed under the MIT License - see the [License](license.md) page for 
details.
