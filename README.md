# gedixr

Handle that mess of [GEDI L2A/L2B](https://gedi.umd.edu/) files and start working with them as a `geopandas.GeoDataFrame` or `xarray.Dataset` in no time!

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
When you download<sup>1</sup> GEDI L2A/L2B v002 files from [NASA Earthdata Search](https://search.earthdata.nasa.gov/search?q=gedi+v002), 
you will end up with a bunch of zipped HDF5 files. After unzipping<sup>1</sup> them, you can use the `extract_data` 
function to recursively find all relevant files in a directory and extract the following biophysical metrics<sup>1</sup> for each shot 
to further work with them as a [`geopandas.GeoDataFrame`](https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoDataFrame.html) or 
[`xarray.Dataset`](https://docs.xarray.dev/en/stable/generated/xarray.Dataset.html):

**L2A**:
- `rh98`: Relative height metrics at 98% interval

**L2B**:
- `rh100`: Height above ground of the received waveform signal start (rh101 from L2A)
- `tcc`: Total canopy cover
- `fhdi`: Foliage Height Diversity
- `pai`: Total Plant Area Index

_See also the following sources for overviews of the layers contained in each product: [L2A](https://lpdaac.usgs.gov/products/gedi02_av002/) and [L2B](https://lpdaac.usgs.gov/products/gedi02_bv002/)_

Note, that for each shot the shot number, acquisition time and geolocation information are also extracted. Furthermore, 
the shots will automatically quality filtered based on the `quality_flag`, `degrade_flag` and `sensitivity`.

Here is an example on how to extract the listed metrics from L2A and L2B files (located in the same directory) for a specific region of interest, which is 
provided as a vector file (e.g. GeoJSON):
```python
from gedixr.gedi import extract_data
from gedixr.xr import merge_gdf, gdf_to_xr

gedi_dir = "directory/containing/gedi/products"  # will be searched recursively
vec_path = "path/to/aoi.geojson"  # any fiona supported vector format should work

# Extract data from GEDI L2A and L2B products for a region of interest
gdf_l2a = extract_data(directory=gedi_dir, gedi_product='L2A', only_full_power=True, subset_vector=vec_path)
gdf_l2b = extract_data(directory=gedi_dir, gedi_product='L2B', only_full_power=True, subset_vector=vec_path)

# Merge into a single GeoDataFrame and rasterize to an xarray Dataset (default: 30 m pixel spacing)
gdf = merge_gdf(gdf_l2a=gdf_l2a, gdf_l2b=gdf_l2b)
xr_ds = gdf_to_xr(gdf=gdf)
```

In case you exported the extracted data to GeoPackage files and want to load them back into a merged `geopandas.GeoDataFrame` and/or `xarray.Dataset`,
you can use the `xr.gpkg_to_gdf` function:
```python
from gedixr.xr import gpkg_to_gdf, gdf_to_xr

gdf = gpkg_to_gdf(gpkg_l2a="path/to/l2a.gpkg", gpkg_l2b="path/to/l2b.gpkg")  # `merge_gdf` is called internally when both arguments are provided
xr_ds = gdf_to_xr(gdf=gdf)
```

<sup>1</sup>See [Limitations](#limitations) section below for relevant notes!

## Limitations
- The scripts only work with GEDI L2A/L2B **V002** products.
- You will need to download the products yourself, however, a solution is work in progress and being tracked in [#1](https://github.com/maawoo/gedixr/issues/1). I'm using [NASA Earthdata Search](https://search.earthdata.nasa.gov/search?q=gedi+v002) to find and download the products.
- The products need to be unzipped first which can seriously increase the amount of disk space needed (~90 MB compressed -> ~3 GB uncompressed... per file!). A solution is work in progress and being tracked in [#2](https://github.com/maawoo/gedixr/issues/2).
- A limited amount of variables can currently be extracted, which are based on my needs. However, I am open to suggestions and pull requests!
