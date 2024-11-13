import pandas as pd
import geopandas as gp
from geocube.api.core import make_geocube

from typing import Optional
from pathlib import Path
from geopandas import GeoDataFrame
from xarray import Dataset


def load_to_gdf(l2a: Optional[str | Path] = None,
                l2b: Optional[str | Path] = None
                ) -> GeoDataFrame:
    """
    Loads GEDI L2A and/or L2B GeoParquet or GeoPackage files as GeoDataFrames. 
    If both are provided, they will be merged into a single GeoDataFrame.
    
    Parameters
    ----------
    l2a: str or Path, optional
        Path to a GEDI L2A GeoParquet or GeoPackage file.
    l2b: str or Path, optional
        Path to a GEDI L2B GeoParquet or GeoPackage file.
    
    Returns
    -------
    final_gdf: GeoDataFrame
        GeoDataFrame containing the data from the provided GEDI L2A and/or L2B files.
    """
    if all(x is None for x in [l2a, l2b]):
        raise RuntimeError("At least one of the parameters 'l2a' or "
                           "'l2b' must be provided!")
    elif all(x is not None for x in [l2a, l2b]):
        gdf_l2a = _reader(l2a)
        gdf_l2b = _reader(l2b)
        final_gdf = merge_gdf(l2a=gdf_l2a, l2b=gdf_l2b)
    else:
        fp = l2a if l2a is not None else l2b
        final_gdf = _reader(fp)
        final_gdf['acq_time'] = pd.to_datetime(final_gdf['acq_time'])
    return final_gdf


def _reader(fp: str | Path) -> GeoDataFrame:
    """Reads a GeoParquet or GeoPackage file as a GeoDataFrame."""
    if isinstance(fp, str):
        fp = Path(fp)
    if fp.suffix == '.gpkg':
        return gp.read_file(fp)
    elif fp.suffix == '.parquet':
        return gp.read_parquet(fp)
    else:
        raise RuntimeError(f"{fp.suffix} not supported")


def merge_gdf(l2a: GeoDataFrame | dict,
              l2b: GeoDataFrame | dict,
              how: str = 'inner',
              on: Optional[str | list[str]] = None
              ) -> GeoDataFrame | dict:
    """
    Merges the data of two GeoDataFrames containing GEDI L2A and L2B data. If
    dictionaries are provided, the function assumes key, value pairs of the dictionary
    output of `gedi.extract_data`. The function will merge the data of matching
    geometries and return a dictionary of GeoDataFrames.
    
    Parameters
    ----------
    l2a: GeoDataFrame or dict
        GeoDataFrame or a dictionary of GeoDataFrames containing GEDI L2A data.
    l2b: GeoDataFrame or dict
        GeoDataFrame or a dictionary of GeoDataFrames containing GEDI L2B data.
    how: str, optional
        The type of merge to be performed. Default is 'inner'.
    on: str or list of str, optional
        The column(s) to merge on. Default is ['geometry', 'shot', 'acq_time'].
    
    Returns
    -------
    merged_out: GeoDataFrame or dict
        A GeoDataFrame or a dictionary of GeoDataFrames containing the merged
        GEDI L2A and L2B data.
    """
    suffixes = ('_l2a', '_l2b')
    if on is None:
        on = ['geometry', 'shot', 'acq_time']
    if all([isinstance(gdf, dict) for gdf in [l2a, l2b]]):
        if len(l2a.keys()) != len(l2b.keys()):
            print(f"WARNING: The provided dictionaries contain data from a "
                  f"different number of geometries: "
                  f"({len(l2a.keys())} vs. {len(l2b.keys())})."
                  f"\nOnly data of matching geometries will be merged and returned.")
        
        matched = set(l2a.keys()).intersection(set(l2b.keys()))
        if len(matched) == 0:
            raise RuntimeError("No matching geometries found between the provided "
                               "dictionaries.")
        
        merged_out = {}
        for aoi in matched:
            _run_checks(l2a[aoi], l2b[aoi], key=aoi)
            merged_gdf = l2b[aoi]['gdf'].merge(l2a[aoi]['gdf'],
                                               how=how, on=on, suffixes=suffixes)
            merged_out[aoi] = {}
            merged_out[aoi]['gdf'] = merged_gdf
            merged_out[aoi]['geo'] = l2a[aoi]['geo']
    elif all([isinstance(gdf, GeoDataFrame) for gdf in [l2a, l2b]]):
        _compare_gdfs(l2a, l2b)
        merged_out = l2b.merge(l2a, how=how, on=on, suffixes=suffixes)
    else:
        raise RuntimeError("The provided input is not supported.")
    return merged_out


def _run_checks(dict_1: dict,
                dict_2: dict,
                key=None) -> None:
    """Helper function to run checks on two GeoDataFrames to be merged."""
    if key is None:
        key = ''
    else:
        key = f" of geometry '{key}')"
        if not dict_1['geo'] == dict_2['geo']:
            raise RuntimeError(f"The GeoDataFrames{key} contain data from "
                               f"different geometries, even though they should"
                               f" match according to their name.")
    _compare_gdfs(dict_1['gdf'], dict_2['gdf'], key=key)


def _compare_gdfs(gdf_1: GeoDataFrame,
                  gdf_2: GeoDataFrame,
                  key=None) -> None:
    """Helper function to compare two GeoDataFrames to be merged."""
    if not gdf_1.crs == gdf_2.crs:
        raise RuntimeError(f"The GeoDataFrames{key} are projected in "
                           f"different coordinate reference systems.")
    if len(gdf_1) != len(gdf_2):
        print(f"WARNING: The GeoDataFrames{key} contain different "
              f"number of rows ({len(gdf_1)} vs. {len(gdf_2)})."
              f"\nThey will be merged nonetheless, which may result in "
              f"unexpected results and/or missing data.")


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
