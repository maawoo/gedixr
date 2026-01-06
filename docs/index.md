# gedixr

Extract the variables you need from [GEDI L2A/L2B](https://gedi.umd.edu/) files 
and start working with them as a `geopandas.GeoDataFrame` or `xarray.Dataset` in 
no time!

## Features

- **Command-line interface** for quick data extraction
- **Logging** to monitor extraction progress and issues
- **Quality filtering** built-in with the option to skip and apply custom filters later
- **Spatial subsetting** using vector files (GeoJSON, GeoPackage, etc.)
- **GeoParquet output** for efficient storage and processing

## Quick Example

=== "CLI"

    ```bash
    # Extract L2B data
    gedixr extract /path/to/gedi/data --product L2B
    
    # Extract L2A data with spatial subset
    gedixr extract /path/to/gedi/data --product L2A -v my_area.geojson
    ```

=== "Python"

    ```python
    from gedixr.gedi import extract_data
    
    # Extract L2B data
    gdf_l2b = extract_data(directory="path/to/data", gedi_product='L2B')

    # Extract L2A data with spatial subset
    gdf_l2a = extract_data(
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

The Global Ecosystem Dynamics Investigation (GEDI) is a NASA mission that provides high-resolution laser ranging observations of the 3D structure of the Earth's forests and topography. Learn more at [gedi.umd.edu](https://gedi.umd.edu/).

## License

This project is licensed under the MIT License - see the [License](license.md) page for details.
