import pandas as pd
import geopandas as gp
from geocube.api.core import make_geocube

from typing import Optional
from pathlib import Path
from geopandas import GeoDataFrame
from xarray import Dataset


def gpkg_to_gdf(gpkg_l2a: Optional[str | Path] = None,
                gpkg_l2b: Optional[str | Path] = None
                ) -> GeoDataFrame:
    """
    Loads GEDI L2A and/or L2B Geopackage files as GeoDataFrames. If both are
    provided, they will be merged into a single GeoDataFrame.
    
    Parameters
    ----------
    gpkg_l2a: str or Path, optional
        Path to a GEDI L2A Geopackage file.
    gpkg_l2b: str or Path, optional
        Path to a GEDI L2B Geopackage file.
    
    Returns
    -------
    final_gdf: GeoDataFrame
        GeoDataFrame containing the data from the provided GEDI L2A and/or L2B
        Geopackage files.
    """
    if all(x is None for x in [gpkg_l2a, gpkg_l2b]):
        raise RuntimeError("At least one of the parameters 'gpkg_l2a' or "
                           "'gpkg_l2b' must be provided!")
    elif all(x is not None for x in [gpkg_l2a, gpkg_l2b]):
        gdf_l2a = gp.read_file(gpkg_l2a)
        gdf_l2b = gp.read_file(gpkg_l2b)
        final_gdf = merge_gdf(gdf_l2a=gdf_l2a, gdf_l2b=gdf_l2b)
    else:
        gpkg = gpkg_l2a if gpkg_l2a is not None else gpkg_l2b
        final_gdf = gp.read_file(gpkg)
        final_gdf['acq_time'] = pd.to_datetime(final_gdf['acq_time'])
    return final_gdf


def merge_gdf(gdf_l2a: GeoDataFrame,
              gdf_l2b: GeoDataFrame
              ) -> GeoDataFrame:
    """
    Merges two GEDI L2A and L2B GeoDataFrames on their `geometry` column.
    
    Parameters
    ----------
    gdf_l2a: GeoDataFrame
        GeoDataFrame containing GEDI L2A data.
    gdf_l2b: GeoDataFrame
        GeoDataFrame containing GEDI L2B data.
    
    Returns
    -------
    merged_gdf: GeoDataFrame
        GeoDataFrame containing the data from the provided GEDI L2A and L2B
        GeoDataFrames.
    """
    if len(gdf_l2a) != len(gdf_l2b):
        print(f"WARNING: The GEDI L2A and L2B GeoDataFrames have different "
              f"number of rows "
              f"({len(gdf_l2a)} vs. {len(gdf_l2b)})."
              f"\nThey will be merged on their geometry column, which may lead "
              f"to unexpected results and/or missing data.")
    gdf_l2a = gdf_l2a.loc[:, ['rh98', 'geometry']]
    merged_gdf = gdf_l2b.merge(gdf_l2a, how='inner', on='geometry')
    merged_gdf['acq_time'] = pd.to_datetime(merged_gdf['acq_time'])
    return merged_gdf


def gdf_to_xr(gdf: GeoDataFrame,
              measurements: Optional[list[str]] = None,
              resolution: Optional[tuple[float, float]] = None
              ) -> Dataset:
    """
    Rasterizes a GeoDataFrame containing GEDI L2A/L2B data to an xarray Dataset.
    
    Parameters
    ----------
    gdf: GeoDataFrame
        GeoDataFrame containing GEDI L2A/L2B data.
    measurements: list of str, optional
        List of measurements names (i.e. GEDI variables) to be included.
        Default is None, which will include all measurements.
    resolution: tuple of float, optional
        A tuple of the pixel spacing of the returned data (Y, X). This includes
        the direction (as indicated by a positive or negative number). Default
        is (-0.0003, 0.0003), which corresponds to a spacing of 30 m.
    
    Returns
    -------
    cube: Dataset
        An xarray Dataset containing the rasterized GEDI data.
    """
    if resolution is None:
        resolution = (-0.0003, 0.0003)
    xr_ds = make_geocube(vector_data=gdf,
                         measurements=measurements,
                         output_crs=f'epsg:{gdf.crs.to_epsg()}',
                         resolution=resolution)
    return xr_ds
