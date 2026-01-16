# Downloading GEDI Data

The `gedixr` package provides functionality to download GEDI data directly using NASA's 
Harmony API. This feature allows you to download GEDI L2A or L2B data for your area and 
time period of interest without manually navigating NASA Earthdata Search.

## Prerequisites and Authentication

Before downloading GEDI data, you need to create a NASA Earthdata account at 
[https://urs.earthdata.nasa.gov/](https://urs.earthdata.nasa.gov/). You might also need 
to configure your credentials for programmatic access. We use the `earthaccess` library 
for handling authentication, which will first look for a `.netrc` file or environment 
variables for your credentials. If you haven't set either up, the library will prompt 
you for your username and password the first time you run a download.  

See their [authentication documentation](https://earthaccess.readthedocs.io/en/stable/user_guide/authenticate/) 
for details.

## Usage

### Basic Example

=== "CLI"

    ```bash
    gedixr download data/gedi \
        --product L2A \
        --time-start 2019-01-01 \
        --time-end 2020-12-31 \
        --subset-vector study_area.geojson
    ```

=== "Python"

    ```python
    files, job_id = download_data(
        directory='data/gedi',
        gedi_product='L2A',
        time_range=('2019-01-01', '2020-12-31'),
        subset_vector='study_area.geojson'
    )
    ```

!!! warning "Bounding Box Subsetting"
    When using `--subset-vector`, the download will be subset to the **bounding box** of 
    the vector geometry, not the exact geometry bounds. This is a current simplification 
    in the download process.
    
    For precise spatial subsetting to your exact area of interest, use the vector file 
    again during the extraction step.

### Hybrid Example: Earthdata Search web interface + gedixr

You can also first use the Earthdata Search web interface to interactively select the 
GEDI data you want with more options to subset the data than currently provided by
`gedixr`. After submitting your request on the Earthdata Search website, you should be 
able to see your request under ['Download Status & History'](https://search.earthdata.nasa.gov/downloads).
After clicking on your request and navigating to "Order Status", you should find an 
"Order ID", which is equivalent to the Harmony job ID. You can then use this job ID to 
download the requested data using `gedixr`:

=== "CLI"

    ```bash
    gedixr download data/gedi \
        --product L2B \
        --job-id your_order_id_here
    ```
=== "Python"

    ```python
    files, job_id = download_data(
        directory='data/gedi',
        gedi_product='L2B',
        job_id='your_order_id_here'
    )
    ```

## Options

### Required Parameters

- `directory`: Directory where files will be saved. A subdirectory named after the 
product (L2A or L2B) will be created automatically.
- `--product` / `-p`: GEDI product type ('L2A' or 'L2B')

### Spatial Subsetting (one required unless resuming with `--job-id`)

- `--subset-vector` / `-v`: Path to vector file for spatial subsetting
- `--bbox`: Bounding box as 'min_lon,min_lat,max_lon,max_lat'

### Temporal Filtering (optional)

- `--time-start` / `-s`: Start date in YYYY-MM-DD format
- `--time-end` / `-e`: End date in YYYY-MM-DD format

!!! note
    Both `--time-start` and `--time-end` must be provided together.

### Resume Options

- `--job-id`: Harmony job ID to resume a previous download

### Other Options

- `--quiet` / `-q`: Suppress progress messages (CLI only)

## Output

Downloaded files are saved in a subdirectory named after the GEDI product within your 
specified directory. E.g., if you download L2B data to `data/gedi/`, the files will be 
saved to:

```
data/gedi/
└── L2B/
    ├── GEDI02_B_2020001000000_O12345_01_T12345_02_005_01_V002.h5
    ├── GEDI02_B_2020002000000_O12346_01_T12346_02_005_01_V002.h5
    └── ...
```

## Python API Return Values

The `download_data` function returns a tuple of:

1. **`file_paths`**: A list of `Path` objects pointing to the downloaded files
2. **`job_id`**: The Harmony job ID (useful for resuming if needed)

```python
files, job_id = download_data(...)

print(f"Downloaded {len(files)} files")
print(f"First file: {files[0]}")
print(f"Job ID: {job_id}")
```

## How It Works

The download process consists of two stages:

1. **Processing**: Harmony processes your request on NASA's servers, subsetting the 
data according to your spatial and temporal filters
2. **Downloading**: Once processing is complete, the files are downloaded to your local 
machine

You'll see progress messages for both stages:

```
Job submitted with ID: abc123def456
Job ID saved to: data/gedi/L2B/.harmony_job_id
Files will be processed by Harmony before proceeding with download...
Processing: 0%
Processing: 9%
Processing: 54%
Processing: 100%
Processing complete. Starting download...
Downloaded 15 file(s) to data/gedi/L2B
```

## Troubleshooting

### Authentication Errors

We use the `earthaccess` library for handling NASA Earthdata authentication. See their 
[authentication documentation](https://earthaccess.readthedocs.io/en/stable/user_guide/authenticate/) 
for setup details. If you encounter authentication errors, verify:

1. Your `.netrc` file exists and has correct permissions
2. Your credentials are correct
3. You've accepted all required Earthdata agreements (check NASA Earthdata website)

### Resuming Interrupted Downloads

Downloads can take considerable time depending on the data volume. If a download is 
interrupted (e.g., network issues, system shutdown), you should be able to resume it 
using the job ID:

=== "CLI"

    ```bash
    # The job ID will be shown when you start the download
    # and saved to a .harmony_job_id file in the download directory
    gedixr download data/gedi \
        --product L2B \
        --job-id abc123def456
    ```

=== "Python"

    ```python
    # Resume using the job_id returned from the initial download
    files, job_id = download_data(
        directory='data/gedi',
        gedi_product='L2B',
        job_id='abc123def456'
    )
    ```

!!! info "Job ID Storage"
    When you start a download, the job ID is automatically saved to a `.harmony_job_id` 
    file in the download directory (e.g., `data/gedi/L2B/.harmony_job_id`). This file is 
    deleted upon successful completion but persists if the download is interrupted.

### Processing Errors

If the Harmony job fails during processing, `gedixr` will:

- Save detailed error information to a JSON file (e.g., `{job_id}_error.json`)
- Display a summary of the errors encountered
- Show which error messages occurred most frequently

Example error output:

```
RuntimeError: Harmony job failed: 75 percent maximum errors exceeded
Error details saved to: data/gedi/L2B/abc123def456_error.json

Total errors: 185
Error summary:
  - 185x: Invalid temporal range, both start and end required.
```

### Large Downloads

For large spatial or temporal extents, downloads can take significant time. Consider:

- Breaking your request into smaller chunks (e.g., by month or sub-regions)
- Using the `--quiet` flag to reduce output
- Running downloads in a `screen` or `tmux` session for long-running processes
- Using the Earthdata Search web interface instead, which may handle large requests more 
robustly.

### Connection Issues

If download is interrupted due to connection issues, simply resume using the `--job-id` 
option with the job ID that was displayed or saved in the `.harmony_job_id` file.

!!! note "Two-Stage Subsetting"
    Notice how the vector file is used in both steps:
    
    1. **Download**: Reduces the amount of data downloaded by subsetting to the vector's 
    bounding box
    2. **Extraction**: Performs precise spatial filtering to the exact vector geometry
    
    This two-stage approach minimizes download time while ensuring accurate spatial 
    subsetting.
