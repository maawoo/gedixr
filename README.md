# gedixr

Extract the variables you need from [GEDI L2A/L2B](https://gedi.umd.edu/) HDF5 files 
and start working with them as a `geopandas.GeoDataFrame` or `xarray.Dataset` in 
no time!

## Features

- **Command-line interface** for quick extraction from a directory of HDF5 files
- **Logging** to monitor extraction progress and issues
- **Quality filtering** built-in with the option to skip and apply custom filters later
- **Spatial subsetting** using common vector file formats (GeoJSON, GeoPackage, etc.)
- **GeoParquet output** for efficient storage and processing

## Quick Start

### Installation

```bash
conda env create --file https://raw.githubusercontent.com/maawoo/gedixr/main/environment.yml
conda activate gedixr_env
pip install git+https://github.com/maawoo/gedixr.git@v0.4.0
```

### CLI Usage

```bash
# Extract default L2B variables
gedixr extract /path/to/gedi/data --product L2B

# Extract default L2A variables with spatial subset
gedixr extract /path/to/gedi/data -p L2A -v my_area.geojson
```

### Python API

```python
from gedixr.gedi import extract_data
from gedixr.xr import merge_gdf

# Extract default L2A and L2B variables
gdf_l2a, out_path_l2a = extract_data(directory="path/to/data", gedi_product='L2A')
gdf_l2b, out_path_l2b = extract_data(directory="path/to/data", gedi_product='L2B')

# Merge GDFs (using inner join)
gdf = merge_gdf(l2a=gdf_l2a, l2b=gdf_l2b)
```

## Documentation

Full documentation is available at: https://maawoo.github.io/gedixr

## License

MIT License - see [LICENSE](LICENSE) for details. 
