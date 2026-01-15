# Quick Start

This guide will help you get started with gedixr in just a few minutes.

## Prerequisites

Before you begin, you'll need GEDI L2A/L2B v002 files. You can download them from 
[NASA Earthdata Search](https://search.earthdata.nasa.gov/search?q=gedi+v002).

If Earthdata Search provided you with zipped files, please unzip them before proceeding.

!!! tip "Spatial Subsetting"
    NASA Earthdata Search allows you to already subset GEDI data to an area of interest 
    during download, which can significantly reduce the amount of data you need to 
    process. You could then use `gedixr`'s spatial subsetting for further refinement 
    if needed (e.g., splitting into multiple study areas).

## Basic Workflow

### 1. Extract data

The following example will:

- Recursively search for GEDI L2B files in the specified directory
- Extract the default data variables for L2B files: rh100, tcc, fhd, pai. (See 
  [Variables](variables.md) for full lists of variables extracted by default.)
- Apply the default quality filtering criteria
- Save results as a GeoParquet file in the `extracted/` subdirectory relative to the 
input directory and log the extraction process in the `log/` subdirectory

=== "CLI"

    ```bash
    gedixr extract /path/to/gedi/data --product L2B
    ```

=== "Python"

    ```python
    from gedixr.extract import extract_data
    
    gdf, out_path = extract_data(
        directory="/path/to/gedi/data",
        gedi_product='L2B'
    )
    ```

#### Optional: Check extraction logs

The extraction process logs errors and warnings. Check the `log/` subdirectory in your 
input directory for detailed information if issues occur.

### 2. Load and merge extracted data

You can load the extracted GeoParquet files back into Python for further analysis using
the `load_to_gdf` function. If you extracted both L2A and L2B data, you can merge them
into a single GeoDataFrame while loading.

```python
from gedixr.xr import load_to_gdf

gdf_merged = load_to_gdf(l2a="extracted/20260106_L2A_1.parquet",
                         l2b="extracted/20260106_L2B_1.parquet")

# or load single product:
gdf_l2b = load_to_gdf(l2b="extracted/20260106_L2B_1.parquet")
```

You can also merge L2A and L2B data directly after extraction using the `merge_gdf` 
function:

```python
from gedixr.extract import extract_data
from gedixr.xr import merge_gdf

# Extract both products
gdf_l2a, out_path_l2a = extract_data(directory="path/to/data", gedi_product='L2A')
gdf_l2b, out_path_l2b = extract_data(directory="path/to/data", gedi_product='L2B')

# Merge them (using inner join)
gdf_merged = merge_gdf(l2a=gdf_l2a, l2b=gdf_l2b)
```

### 3. Explore / Analyze data
Now that you have the data loaded as a `geopandas.GeoDataFrame`, you can start exploring
and analyzing it using `geopandas` and `pandas`, or other related libraries. For 
example, you could use the `xvec` package to extract other environmental variables from 
`xarray` Datasets based on the GEDI shot locations and acquisition times and then train 
a machine learning model for predicting forest structure.

## Overview of extraction options

The main extraction function `extract_data` (or `gedixr extract` CLI command) provides
various options to customize the extraction process. Here is a quick overview of these 
options, which you can combine as needed.

### Quality Filtering

Control whether to apply default quality filters:

=== "CLI"

    ```bash
    # With quality filtering (default)
    gedixr extract /path/to/data --quality-filter
    
    # Without quality filtering
    gedixr extract /path/to/data --no-quality-filter
    ```

=== "Python"

    ```python
    from gedixr.extract import extract_data

    # With quality filtering (default)
    gdf = extract_data(
        directory="/path/to/data",
        apply_quality_filter=True
    )
    
    # Without quality filtering
    gdf = extract_data(
        directory="/path/to/data",
        apply_quality_filter=False
    )
    ```

See [Quality Filtering](quality.md) for detailed information on the default quality
filters applied as well as an example of how to implement custom filtering after 
extraction.

!!! info "Output File Naming"
    The output filename indicates whether quality filtering was applied by using a 
    boolean suffix after the product type:
    `YYYYMMDDHHMMSS_L2B_1.parquet` (filtered data), `YYYYMMDDHHMMSS_L2B_0.parquet` 
    (unfiltered data)


### Spatial Subsetting

Extract data for specific areas using vector files:

=== "CLI"

    ```bash
    # Single area
    gedixr extract /path/to/data -v study_area.geojson
    
    # Multiple areas (creates separate output files per area)
    gedixr extract /path/to/data -v area1.geojson -v area2.geojson
    ```

=== "Python"

    ```python
    from gedixr.extract import extract_data

    # Single area
    gdf = extract_data(
        directory="path/to/data",
        subset_vector="study_area.geojson"
    )
    
    # Multiple areas (returns a dictionary)
    result_dict = extract_data(
        directory="path/to/data",
        subset_vector=["area1.geojson", "area2.geojson"]
    )
    
    # Access individual results
    area1_gdf = result_dict['area1']['gdf']
    area2_gdf = result_dict['area2']['gdf']
    ```

The output GeoParquet file(s) will be saved in the `extracted/` subdirectory with the
vector file basename included in the filename (e.g., 
`YYYYMMDDHHMMSS_L2B_1_study_area.parquet` for the single area example above).

When using multiple vector files, the output dictionary will contain separate entries
for each vector file with the following structure:

```python
{'<Vector Basename>': {'geo': Polygon, 'gdf': GeoDataFrame}}
```

Where `<Vector Basename>` is the name of the vector file without the file extension,
`geo` is the geometry of the area, and `gdf` is the extracted GeoDataFrame for that area.

### Specific Months

Extract only data from certain months (e.g., June to August):

=== "CLI"

    ```bash
    gedixr extract /path/to/data --filter-month-min 6 --filter-month-max 8
    ```

=== "Python"

    ```python
    from gedixr.extract import extract_data

    gdf = extract_data(
        directory="path/to/data",
        filter_month=(6, 8)
    )
    ```

### Specific Beams

Extract data from specific beam types:

=== "CLI"

    ```bash
    # Only power beams
    gedixr extract /path/to/data -b power
    
    # Only coverage beams
    gedixr extract /path/to/data -b coverage
    
    # Specific beams
    gedixr extract /path/to/data -b BEAM0101,BEAM0110
    ```

=== "Python"

    ```python
    from gedixr.extract import extract_data

    # Only power beams
    gdf = extract_data(directory="path/to/data", beams='power')
    
    # Only coverage beams
    gdf = extract_data(directory="path/to/data", beams='coverage')

    # Specific beams
    gdf = extract_data(
        directory="path/to/data",
        beams=['BEAM0101', 'BEAM0110']
    )
    ```

### Custom Variables

Using the Python API, you can specify custom variables to extract using the `variables`
parameter when calling the `extract_data` function. See [Variables](variables.md) for 
more details.

=== "Python"

    ```python
    from gedixr.extract import extract_data

    variables = [
        ('rh50', 'rh50'),
        ('rh75', 'rh75'),
        ('treecover', 'land_cover_data/landsat_treecover')
    ]
    gdf = extract_data(
        directory="/path/to/data",
        gedi_product='L2A',
        variables=variables
    )
    ```
