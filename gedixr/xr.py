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
        final_gdf = merge_gdf(gdf_l2a=gdf_l2a, gdf_l2b=gdf_l2b)
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


def merge_gdf(gdf_l2a: GeoDataFrame,
              gdf_l2b: GeoDataFrame,
              l2a_variables: Optional[list[str]] = None,
              l2b_variables: Optional[list[str]] = None
              ) -> GeoDataFrame:
    """
    Merges two GEDI L2A and L2B GeoDataFrames on their `geometry` column.
    
    Parameters
    ----------
    gdf_l2a: GeoDataFrame
        GeoDataFrame containing GEDI L2A data.
    gdf_l2b: GeoDataFrame
        GeoDataFrame containing GEDI L2B data.
    l2a_variables: list of str, optional
        List of L2A variables to be included in the merged GeoDataFrame.
        Default is None, which will include default rh98 variable.
    l2b_variables: list of str, optional
        List of L2B variables to be included in the merged GeoDataFrame.
        Default is None, which will include default variables.
    
    Returns
    -------
    merged_gdf: GeoDataFrame
        GeoDataFrame containing the data from the provided GEDI L2A and L2B
        GeoDataFrames.
    """
    if type(gdf_l2a)==dict:
        if len(gdf_l2a.keys()) != len(gdf_l2b.keys()):
            print(f"WARNING: The GEDI L2A and L2B GeoDataFrames have different "
                  f"number of AOI's "
                  f"({len(gdf_l2a.keys())} vs. {len(gdf_l2b.keys())})."
                  f"\nThey will be merged per AOI, which may lead "
                  f"to unexpected results and/or missing data.")
        # loop over the aoi's and merge the dataframes
        # get the number of aoi's from the longer dictionary
        nr_aoi = max(len(gdf_l2a.keys()), len(gdf_l2b.keys()))
        unique_keys = set(gdf_l2a.keys()).union(set(gdf_l2b.keys()))
        # if lengdf_l2a.keys() > 1, store the merged gdf in a dictionary
        if nr_aoi > 1:
            # create a dictionary with the aois as keys and an empty placeholder as value for the gdf
            merged_gdf_dict = {aoi: {'gdf': None} for aoi in unique_keys}
        for aoi in gdf_l2a.keys():
            # convert to geodataframe
            gdf_l2a_aoi = gdf_l2a[aoi]['gdf']
            gdf_l2b_aoi = gdf_l2b[aoi]['gdf']
            if len(gdf_l2a) != len(gdf_l2b):
                print(f"WARNING: The GEDI L2A and L2B GeoDataFrames have different "
                    f"number of rows "
                    f"({len(gdf_l2a)} vs. {len(gdf_l2b)})."
                    f"\nThey will be merged on their geometry column, which may lead "
                    f"to unexpected results and/or missing data.")
            if l2a_variables == None:
                gdf_l2a_aoi = gdf_l2a_aoi.loc[:, ['rh98', 'geometry']]
            else:
                gdf_l2a_aoi = gdf_l2a_aoi.loc[:, l2a_variables + ['geometry']]

            merged_gdf = gdf_l2b_aoi.merge(gdf_l2a_aoi, how='inner', on='geometry')
            if nr_aoi > 1:
                # add the merged gdf to the dictionary with aoi as key
                merged_gdf_dict[aoi] = {'gdf': merged_gdf}
            else:
                return merged_gdf
        return merged_gdf_dict

    if len(gdf_l2a) != len(gdf_l2b):
        print(f"WARNING: The GEDI L2A and L2B GeoDataFrames have different "
              f"number of rows "
              f"({len(gdf_l2a)} vs. {len(gdf_l2b)})."
              f"\nThey will be merged on their geometry column, which may lead "
              f"to unexpected results and/or missing data.")
    if l2a_variables == None:
        gdf_l2a = gdf_l2a.loc[:, ['rh98', 'geometry']]
    else:
        gdf_l2a = gdf_l2a.loc[:, l2a_variables + ['geometry']]
    merged_gdf = gdf_l2b.merge(gdf_l2a, how='inner', on='geometry')
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
