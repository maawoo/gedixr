# Quality Filtering

The extraction process automatically applies quality filtering to remove low-quality 
GEDI shots. This ensures that your analysis uses reliable data. From my experience, 
however, the default filters may not be appropriate for all landcover types. Therefore, 
you also have the option to disable quality filtering and implement your own criteria.

## Default Filtering

By default, shots are filtered based on the following conditions:

| Filter | Condition | Description |
|--------|-----------|-------------|
| Quality Flag | `quality_flag == 1` | Shot meets quality standards |
| Degrade Flag | `degrade_flag == 0` | Shot is not in a degraded state |
| Detected Modes | `num_detectedmodes > 0` | At least one mode was detected |
| Elevation Check | `abs(elev - elev_dem_tdx) < 100` | Elevation difference < 100 m from DEM |

!!! info "Beam Sensitivity"
    The `quality_flag` already includes filtering for beam sensitivity in the default 
    range of 0.9 - 1.0, so no additional sensitivity filtering is needed if this is what
    you want.


### Filter Statistics in Logs

During extraction, `gedixr` logs the number and percentage of shots that were filtered 
out if quality filtering is enabled. Example log entry:

```
INFO | GEDI02_B_2024130044637_O30619_04_T06857_02_004_01_V002.h5 | 
  00234/01567 (14.93%) shots were filtered due to poor quality
```

### Output File Naming

The output filename indicates whether default quality filtering was applied by using a 
suffix after the product type:

- `YYYYMMDDHHMMSS_L2B_1.parquet` - Quality filtering was **enabled**
- `YYYYMMDDHHMMSS_L2B_0.parquet` - Quality filtering was **disabled**

## Disabling Quality Filtering

You have the option to disable the default quality filtering during data extraction. In
this case, all shots are included in the output. The `quality_flag` and `degrade_flag` 
columns are still included in the output in addition to other related columns 
(e.g., `sensitivity`), allowing you to apply custom filtering afterward.

=== "CLI"

    ```bash
    gedixr extract /path/to/data --no-quality-filter
    ```

=== "Python"

    ```python
    from gedixr.gedi import extract_data
    
    gdf, out_path = extract_data(
        directory="/path/to/data",
        gedi_product='L2B',
        apply_quality_filter=False
    )
    ```

## Custom Quality Filtering

After extracting data without quality filtering, you can apply your own criteria:

```python
from gedixr.gedi import extract_data

# Extract without default filtering
gdf, out_path = extract_data(
    directory="/path/to/data",
    gedi_product='L2B',
    apply_quality_filter=False
)

# Apply custom filters
gdf_flt = gdf[
    (gdf['quality_flag'] == 1) &
    (gdf['degrade_flag'] == 0) &
    (gdf['num_detectedmodes'] > 0) &
    (gdf['sensitivity'] > 0.95) & # Higher lower bound on beam sensitivity
    (abs(gdf['elev'] - gdf['elev_dem_tdx']) < 50)  # Stricter elevation check
]
```
