import pandas as pd
import geopandas as gp
from geocube.api.core import make_geocube


def gpkg_to_gdf(gpkg_l2a=None, gpkg_l2b=None):
    """
    Loads GEDI L2A and/or L2B Geopackage files as GeoDataFrames. If both are provided, they will be merged into a single
    GeoDataFrame.

    Parameters
    ----------
    gpkg_l2a: str|Path, optional
        Path to a GEDI L2A Geopackage file.
    gpkg_l2b: str|Path, optional
        Path to a GEDI L2B Geopackage file.

    Returns
    -------
    final_gdf: geopandas.GeoDataFrame
        GeoDataFrame containing the data from the provided GEDI L2A and/or L2B Geopackage files.
    """
    if all(x is None for x in [gpkg_l2a, gpkg_l2b]):
        raise RuntimeError("At least one of the parameters 'gpkg_l2a' or 'gpkg_l2b' must be provided!")
    elif all(x is not None for x in [gpkg_l2a, gpkg_l2b]):
        gdf_l2a = gp.read_file(gpkg_l2a)
        gdf_l2b = gp.read_file(gpkg_l2b)
        final_gdf = merge_gdf(gdf_l2a=gdf_l2a, gdf_l2b=gdf_l2b)
    else:
        gpkg = gpkg_l2a if gpkg_l2a is not None else gpkg_l2b
        final_gdf = gp.read_file(gpkg)
        final_gdf['acq_time'] = pd.to_datetime(final_gdf['acq_time'])
    return final_gdf


def merge_gdf(gdf_l2a, gdf_l2b):
    """
    Merges two GEDI L2A and L2B GeoDataFrames on their `geometry` column.

    Parameters
    ----------
    gdf_l2a: geopandas.GeoDataFrame
        GeoDataFrame containing GEDI L2A data.
    gdf_l2b: geopandas.GeoDataFrame
        GeoDataFrame containing GEDI L2B data.

    Returns
    -------
    merged_gdf: geopandas.GeoDataFrame
        GeoDataFrame containing the data from the provided GEDI L2A and L2B GeoDataFrames.
    """
    if len(gdf_l2a) != len(gdf_l2b):
        print(f"WARNING: The GEDI L2A and L2B GeoDataFrames have different number of rows "
              f"({len(gdf_l2a)} vs. {len(gdf_l2b)})."
              f"\nThey will be merged on their geometry column, which may lead to unexpected results and/or missing "
              f"data.")
    gdf_l2a = gdf_l2a.loc[:, ['rh98', 'geometry']]
    merged_gdf = gdf_l2b.merge(gdf_l2a, how='inner', on='geometry')
    merged_gdf['acq_time'] = pd.to_datetime(merged_gdf['acq_time'])
    return merged_gdf


def gdf_to_xr(gdf, gedi_vars=None, resolution=None):
    """
    Rasterizes a GeoDataFrame containing GEDI L2A/L2B data to an xarray Dataset.
    
    Parameters
    ----------
    gdf: geopandas.GeoDataFrame
        GeoDataFrame containing GEDI L2A/L2B data.
    gedi_vars: list(str)
        List of attribute names (i.e. GEDI variables) to be included. Defaault is None, which will include all
        variables.
    resolution:
        A tuple of the pixel spacing of the returned data (Y, X). This includes the direction
        (as indicated by a positive or negative number). Default is (-0.0003, 0.0003), which corresponds to a spacing
        of 30 m.
    
    Returns
    -------
    cube: xarray.Dataset
        An xarray Dataset containing the rasterized GEDI data.
    """
    if resolution is None:
        resolution = (-0.0003, 0.0003)
    xr_ds = make_geocube(gdf, measurements=gedi_vars, output_crs=f'epsg:{gdf.crs.to_epsg()}', resolution=resolution)
    return xr_ds
