# gedixr

Extract the variables you need from [GEDI L2A/L2B](https://gedi.umd.edu/) files 
and start working with them as a `geopandas.GeoDataFrame` or `xarray.Dataset` in 
no time!

## Installation
### Latest state on GitHub
1. Create and activate an environment with the required dependencies:
```bash
conda env create --file https://raw.githubusercontent.com/maawoo/gedixr/main/environment.yml
conda activate gedixr_env
```
I recommend you to check [Mamba/Micromamba](https://mamba.readthedocs.io/en/latest/index.html) 
as a faster alternative to Conda.

2. Install the `gedixr` package into the activated environment:
```bash
pip install git+https://github.com/maawoo/gedixr.git
```

### Specific version
See the [Tags](https://github.com/maawoo/gedixr/tags) section of the repository
for available versions to install:
```bash
conda env create --file https://raw.githubusercontent.com/maawoo/gedixr/v0.4.0/environment.yml
conda activate gedixr_env
pip install git+https://github.com/maawoo/gedixr.git@v0.4.0
```

## Usage

After downloading GEDI L2A/L2B v002 files from [NASA Earthdata Search](https://search.earthdata.nasa.gov/search?q=gedi+v002)<sup>1</sup>, 
you will end up with a bunch of zipped HDF5 files. After unzipping<sup>2</sup> them, 
you can extract biophysical variables (see [here](#extracted-variables) 
for defaults) for each shot using either the command-line interface or the Python API. 
The extracted data will be saved as GeoParquet files and can be further worked with 
as `geopandas.GeoDataFrame` in Python or used in your favorite GIS software.

### Command Line Interface (CLI)

After installation, you can use the `gedixr` command-line tool:

```bash
# Extract L2B data from a directory (with default quality filtering)
gedixr extract /path/to/gedi/data --product L2B

# Extract L2A data without quality filtering
gedixr extract /path/to/gedi/data -p L2A --no-quality-filter

# Extract only from power beams
gedixr extract /path/to/gedi/data -b full

# Filter by month range (e.g., June to August)
gedixr extract /path/to/gedi/data --filter-month-min 6 --filter-month-max 8

# Subset to specific areas (creates separate output files per area)
gedixr extract /path/to/gedi/data -v aoi_1.geojson -v aoi_2.geojson

# Extract from zip files without permanently unpacking them
gedixr extract /path/to/gedi/data --temp-unpack-zip

# Show version
gedixr version
```

Use `gedixr extract --help` for all available options.

### Python API

You can import the `extract_data` function to use the extraction functionality in
your Python scripts or Jupyter notebooks.

#### Basic example
The NASA Earthdata Search platform mentioned above allows you to already subset
the GEDI data to your area of interest during the download process. This saves 
you space on disk and the extraction process is quite straightforward in this 
case:
```python
from gedixr.gedi import extract_data

gedi_dir = "directory/containing/gedi/products"
gdf_l2a = extract_data(directory=gedi_dir, gedi_product='L2A')
gdf_l2b = extract_data(directory=gedi_dir, gedi_product='L2B')
```

The `directory` you provide will be searched recursively and only files will be 
considered that match the product provided via the `gedi_product` parameter.

If you extracted variables from L2A and L2B files of the same spatial and temporal 
extents, you can then merge both GeoDataFrames:
```python
from gedixr.xr import merge_gdf

gdf = merge_gdf(l2a=gdf_l2a, l2b=gdf_l2b)
```

If you want to rasterize the GeoDataFrame and use the data as an `xarray.Dataset`:
```python
from gedixr.xr import gdf_to_xr

ds = gdf_to_xr(gdf=gdf)
```

If you want to load previously extracted data:
```python
from gedixr.xr import load_to_gdf

gdf = load_to_gdf(l2a="path/to/extracted_l2a.parquet")
```

#### Custom subsetting
If your GEDI data is not subsetted (i.e., each file covering an entire orbit), 
you can provide a vector file (e.g. GeoJSON, GeoPackage, etc.) to extract 
metrics for your area of interest. You can also provide a list of vector files 
to extract for multiple areas at the same time:
```python
from gedixr.gedi import extract_data

l2a_dict = extract_data(directory="directory/containing/gedi/products", 
                        gedi_product='L2A', 
                        subset_vector=["path/to/aoi_1.geojson",
                                       "path/to/aoi_2.geojson"])
```

Please note that if the `subset_vector` parameter is used, a dictionary with the 
following key, value pairs is returned:
```
{'<Vector Basename>': {'geo': Polygon, 'gdf': GeoDataFrame}}
```

Given the above example, you can access the extracted GeoDataFrame of each area
like this:
```python
aoi_1_gdf = l2a_dict['aoi_1']['gdf']
aoi_2_gdf = l2a_dict['aoi_2']['gdf']
```

#### Extract from specific beams 
The `beams` parameter can be used to specify which beams to extract data from. 
By default, data will be extracted from all beams (full power and coverage). You 
can use `beams='full'` (or `'coverage'`) to only extract from one or the other. 
Alternatively, you can provide a list of beam names, e.g.: 
`beams=['BEAM0101', 'BEAM0110']`

## Current defaults
### Extracted variables
In addition to shot number, acquisition time and geolocation information, the
following variables are extracted by default if no custom variables are provided 
via the `variables` parameter:

**L2A**:
- `rh98`: Relative height metrics at 98% interval

**L2B**:
- `rh100`: Height above ground of the received waveform signal start (`rh101` from L2A)
- `tcc`: Total canopy cover
- `fhd`: Foliage Height Diversity
- `pai`: Total Plant Area Index

_See also the following sources for overviews of the layers contained in each 
product: [L2A](https://lpdaac.usgs.gov/products/gedi02_av002/) and [L2B](https://lpdaac.usgs.gov/products/gedi02_bv002/)_

### Quality filtering
The extraction process will automatically apply quality filtering based on the 
following conditions:
- `quality_flag` == 1 
- `degrade_flag` == 0
- `num_detectedmodes` > 0
- abs(`elev` - `elev_dem_tdx`) < 100

Please note that `quality_flag` already includes filtering to a `sensitivity` 
range of 0.9 - 1.0. 

If you want to apply a different quality filtering strategy, you can disable the
default filtering by setting `apply_quality_filter=False` (Python API) or using 
`--no-quality-filter` (CLI) and apply your own filtering after the extraction process.

## Notes
<sup>1</sup>See [#1](https://github.com/maawoo/gedixr/issues/1) for a related issue regarding the download of GEDI data.

<sup>2</sup>The products need to be unzipped first which can seriously increase 
the amount of disk space needed (~90 MB compressed -> ~3 GB uncompressed... per 
file!). Alternatively, you can use the `temp_unpack_zip=True` parameter (Python API) 
or `--temp-unpack-zip` flag (CLI) to extract from zip files using temporary directories, 
though this may be slower. 
