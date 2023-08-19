# gedixr

Handle that mess of GEDI L2A/L2B files and start working with them as a GeoDataFrame or xarray Dataset in no time!

## Installation

1. Create and activate an environment with the required dependencies:
```bash
conda env create --file https://raw.githubusercontent.com/maawoo/gedixr/main/environment.yml
conda activate gedixr_env
```
I recommend you to check [Mambaforge](https://github.com/conda-forge/miniforge#mambaforge) or 
[Micromamba](https://mamba.readthedocs.io/en/latest/user_guide/micromamba.html) as faster alternatives to Conda.

2. Install the `gedixr` package into the activated environment:
```bash
pip install git+https://github.com/maawoo/gedixr.git
```

## Usage

```python
from gedixr.gedi import extract_data
from gedixr.xr import merge_gdf, gdf_to_xr

gedi_dir = "directory/containing/gedi/products"  # will be searched recursively
vec_path = "path/to/aoi.geojson"  # any fiona supported vector format should work

# Extract data from GEDI L2A and L2B products for a region of interest
gdf_l2a = extract_data(directory=gedi_dir, gedi_product='L2A', only_full_power=True, subset_vector=vec_path)
gdf_l2b = extract_data(directory=gedi_dir, gedi_product='L2B', only_full_power=True, subset_vector=vec_path)

# Merge into a single GeoDataFrame and rasterize to an xarray Dataset (default = 30 m pixel spacing)
gdf = merge_gdf(gdf_l2a=gdf_l2a, gdf_l2b=gdf_l2b)
xr_ds = gdf_to_xr(gdf=gdf)
```

## Limitations

- The scripts only work with GEDI L2A/L2B **V002** products.
- You will need to download the products yourself, however, a solution is work in progress and being tracked in #1. I'm using [NASA Earthdata Search](https://search.earthdata.nasa.gov/search?q=gedi+v002) to find and download the products.
- The products need to be unzipped first which can seriously increase the amount of disk space needed (~90 MB compressed -> ~3 GB uncompressed... per file!). A solution is work in progress and being tracked in #2.
- A limited amount of variables can currently be extracted, which are based on my needs. However, I am open to suggestions and pull requests!
