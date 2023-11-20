from pathlib import Path
import warnings
import logging
from tqdm import tqdm
import h5py
import pandas as pd
import geopandas as gp
from shapely.geometry import Point
from shapely.errors import ShapelyDeprecationWarning

import gedixr.ancillary as ancil

ALLOWED_PRODUCTS = ['L2A', 'L2B']

FULL_POWER_BEAMS = ['BEAM0101', 'BEAM0110', 'BEAM1000', 'BEAM1011']

VARIABLES_BASIC_L2A = [('Shot Number', 'shot_number'),
                       ('Latitude', 'lat_lowestmode'),
                       ('Longitude', 'lon_lowestmode'),
                       ('Degrade Flag', 'degrade_flag'),
                       ('Quality Flag', 'quality_flag'),
                       ('Sensitivity', 'sensitivity'),
                       ('Relative Height bin95 (cm)', 'rh95'),
                       ('Relative Height bin98 (cm)', 'rh98')]

VARIABLES_BASIC_L2B = [('Shot Number', 'shot_number'),
                       ('Latitude', 'geolocation/lat_lowestmode'),
                       ('Longitude', 'geolocation/lon_lowestmode'),
                       ('Degrade Flag', 'geolocation/degrade_flag'),
                       ('Quality Flag', 'l2b_quality_flag'),
                       ('Sensitivity', 'sensitivity'),
                       ('Total Canopy Cover', 'cover'),
                       ('Foliage Height Diversity Index', 'fhd_normal'),
                       ('Total Plant Area Index', 'pai')]


def extract_data(directory, gedi_product='L2B', only_full_power=True, filter_month=(1, 12), variables=None, beams=None,
                 subset_vector=None, save_gpkg=True, dry_run=False):
    """
    Extracts data from GEDI L2A or L2B files in HDF5 format using the following steps:
    
    (1) Search a root directory recursively for GEDI L2A or L2B HDF5 files.
    (2) OPTIONAL: Filter files by month of acquisition and the respective beams (full power or not).
    (3) Extract general, quality and analysis related information from each file into a pandas.Dataframe.
    (4) Filter out shots of poor quality.
    (5) Convert Dataframe to GeoDataFrame and add a 'geometry' column containing a shapely.geometry.Point objects.
    (6) OPTIONAL: Subset shots spatially using intersection via provided vector file or list of vector files.
    (7) OPTIONAL: Save the results as a GeoPackage file or multiple files (one per provided vector file).
    (8) Return a GeoDataFrame or dictionary of GeoDataFrame objects (one per provided vector file).
    
    Parameters
    ----------
    directory: str or Path
        Root directory to recursively search for GEDI L2A/L2B files.
    gedi_product: str, optional
        GEDI product type. Either 'L2A' or 'L2B'. Default is 'L2B'.
    filter_month: tuple(int), optional
        Filter GEDI shots by month of the year? E.g. (6, 8) to only keep shots that were acquired between June 1st and
        August 31st of each year. Defaults to (1, 12), which keeps all shots of each year.
    subset_vector: str|Path or list(str|Path), optional
        Path or list of paths to vector files in a fiona supported format to subset the GEDI data spatially. Default is
        None, to keep all shots. Note that the basename of each vector file will be used in the output names, so it is
        recommended to give those files reasonable names beforehand!
    variables: list(tuple(str)), optional
        List of tuples containing the variable name and the respective GEDI layer name. Defaults to
        `gedixr.gedi.VARIABLES_BASIC_L2A` for L2A products and `gedixr.gedi.VARIABLES_BASIC_L2B` for L2B products.
    beams: list(str), optional
        List of GEDI beams to extract values from. Defaults to full power beams:
        ['BEAM0101', 'BEAM0110', 'BEAM1000', 'BEAM1011']
    save_gpkg: bool, optional
        Save resulting GeoDataFrame as a Geopackage file in a subdirectory called `extracted` of the directory specified
        with `gedi_dir`? Default is True.
    dry_run: bool, optional
        If set to True, will only print out how many GEDI files were found. Default is False.
    
    Returns
    -------
    geopandas.geodataframe.GeoDataFrame or dictionary of geopandas.geodataframe.GeoDataFrame
        The key-value pairs in case of an output dictionary:
            {'<Vector Basename>': {'geo': shapely.geometry.polygon.Polygon,
                                   'gdf': geopandas.geodataframe.GeoDataFrame}
            }
    """
    if gedi_product not in ALLOWED_PRODUCTS:
        raise RuntimeError(f"Parameter 'gedi_product': expected to be one of {ALLOWED_PRODUCTS}; "
                           f"got {gedi_product} instead")
    
    directory = ancil.to_pathlib(x=directory)
    subset_vector = ancil.to_pathlib(x=subset_vector) if subset_vector is not None else None
    log_handler, now = ancil.set_logging(directory, gedi_product)
    n_err = 0
    
    if subset_vector is not None:
        # https://gis.stackexchange.com/a/433423
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=ShapelyDeprecationWarning)
        out_dict = ancil.prepare_roi(vec=subset_vector)
    
    if beams is None:
        beams = FULL_POWER_BEAMS
    
    if variables is None:
        if gedi_product == 'L2A':
            variables = VARIABLES_BASIC_L2A
        else:
            variables = VARIABLES_BASIC_L2B
    
    # (1) Search for GEDI files
    pattern = f'*GEDI02_{gedi_product[-1]}*.h5'
    filepaths = [p for p in directory.rglob('*') if p.is_file() and p.match(pattern)]
    if dry_run:
        print(f"{len(filepaths)} GEDI {gedi_product} files were found to extract data from. "
              f"Rerun without activated 'dry_run'-flag to extract data.")
        return None
    if len(filepaths) == 0:
        raise RuntimeError(f"No GEDI {gedi_product} files were found in {directory}.")
    
    gdf_list_no_spatial_subset = []
    for i, fp in enumerate(tqdm(filepaths)):
        
        # (2) Filter by month of acquisition and beam type
        date = ancil.date_from_gedi_file(gedi_path=fp)
        if not filter_month[0] <= date.month <= filter_month[1]:
            msg = f'Time of acquisition outside of filter range: month_min={filter_month[0]}, ' \
                  f'month_max={filter_month[1]}'
            ancil.log(handler=log_handler, mode='info', file=fp.name, msg=msg)
            continue
        
        try:
            gedi = h5py.File(fp, 'r')
            
            # (3) Extract data and convert to Dataframe
            df = pd.DataFrame(_from_file(gedi_file=gedi, beams=beams, variables=variables, acq_time=date))
            
            # (4) Filter by quality flags
            df = filter_quality(df=df, log_handler=log_handler, gedi_path=fp)
            
            # (5) Convert to GeoDataFrame and set 'Shot Number' as index
            df['geometry'] = df.apply(lambda row: Point(row.longitude, row.latitude), axis=1)
            df = df.drop(columns=['latitude', 'longitude'])
            gdf = gp.GeoDataFrame(df)
            gdf.crs = 'EPSG:4326'
            
            # (6) Subset spatially if any vector files were provided
            if subset_vector is not None:
                for k, v in out_dict.items():
                    gdf_sub = gdf[gdf.intersects(v['geo'])]
                    if not gdf_sub.empty:
                        if out_dict[k]['gdf'] is None:
                            out_dict[k]['gdf'] = gdf_sub
                        else:
                            out_dict[k]['gdf'] = pd.concat([out_dict[k]['gdf'], gdf_sub])
                    del gdf_sub
            else:
                gdf_list_no_spatial_subset.append(gdf)
            
            gedi.close()
            del df, gdf
        
        except Exception as msg:
            ancil.log(handler=log_handler, mode='exception', file=fp.name, msg=str(msg))
            n_err += 1
    
    try:
        # (7) & (8)
        out_dir = directory / 'extracted'
        out_dir.mkdir(exist_ok=True)
        if subset_vector is not None:
            if save_gpkg:
                for vec_base, _dict in out_dict.items():
                    if _dict['gdf'] is not None:
                        out_gpkg = out_dir / (now + f'__{gedi_product}_' + '_subset_' + vec_base + '.gpkg')
                        _dict['gdf'].to_file(out_gpkg, driver='GPKG')
            return out_dict
        else:
            out = pd.concat(gdf_list_no_spatial_subset)
            if save_gpkg:
                out_gpkg = out_dir / (now + f'__{gedi_product}' + '.gpkg')
                out.to_file(out_gpkg, driver='GPKG')
            return out
    except Exception as msg:
        ancil.log(handler=log_handler, mode='exception', msg=str(msg))
        n_err += 1
    finally:
        ancil.close_logging(log_handler=log_handler)
        if n_err > 0:
            print(f"WARNING: {n_err} errors occurred during the extraction process. Please check the log file!")


def _from_file(gedi_file, beams, variables, acq_time='Acquisition Time'):
    """
    Extracts general(*), quality(**) and analysis(***) related values from a GEDI HDF5 file.
    Variables can be adjusted by providing a variable list of tuples containing the variable
    name and the respective GEDI layer name.
    
    L2A:
    (*)   `/<BEAM>/shot_number`, `/<BEAM>/lon_lowestmode`, `/<BEAM>/lat_lowestmode`
    (**)  `/<BEAM>/degrade_flag`, `/<BEAM>/quality_flag`, `/<BEAM>/sensitivity`
    (***) `/<BEAM>/rh[98]*100` (98th bin converted to cm)

    L2B:
    (*)   `/<BEAM>/shot_number`, `/<BEAM>/geolocation/lon_lowestmode`, `/<BEAM>/geolocation/lat_lowestmode`
    (**)  `/<BEAM>/geolocation/degrade_flag`, `/<BEAM>/l2b_quality_flag`, `/<BEAM>/sensitivity`
    (***) `/<BEAM>/cover`, `/<BEAM>/fhd_normal`, `/<BEAM>/pai`, `/<BEAM>/rh100`
    
    Parameters
    ----------
    gedi_file: h5py._hl.files.File
        A loaded GEDI L2A HDF5 file.
    beams: list(str)
        List of GEDI beams to extract values from.
    acq_time: datetime.datetime
        Acquisition date of the GEDI HDF5 file.
    
    Returns
    -------
    out: dict
        Dictionary containing extracted values.
    """
    out = {}
    for beam in beams:
        for k, v in variables:
            if v.startswith('rh') and v != 'rh100':
                out[k] = [round(h[int(v[2:])] * 100) for h in gedi_file[f'{beam}/rh'][()]]
            elif v == 'shot_number':
                out[k] = [str(h) for h in gedi_file[f'{beam}/{v}'][()]]
            else:
                out[k] = gedi_file[f'{beam}/{v}'][()]
    
    out['acq_time'] = [(str(acq_time)) for _ in range(len(out['Shot Number']))]
    return out


def filter_quality(df, log_handler, gedi_path):
    """
    Filters a given pandas.Dataframe containing GEDI data using its quality flags. The values used here have been
    adopted from the official GEDI L2A/L2B tutorials:
    https://git.earthdata.nasa.gov/projects/LPDUR/repos/gedi-v2-tutorials/browse
    
    Parameters
    ----------
    df: :obj:`pandas.Dataframe`
        Dataframe containing data of the GEDI L2A/L2B file.
    log_handler: logging.Logger
        Current log handler.
    gedi_path: Path
        Path to the current GEDI L2A/L2B file.
    
    Returns
    -------
    df: pandas.Dataframe
        The quality-filtered dataframe.
    """
    len_before = len(df)
    df = df.where(df['quality_flag'].ne(0))
    df = df.where(df['degrade_flag'] < 1)
    df = df.where(df['sensitivity'] > 0.95)
    df = df.dropna()
    df = df.drop(columns=['quality_flag', 'degrade_flag', 'sensitivity'])
    len_after = len_before - len(df)
    filt_perc = round((len_after / len_before) * 100, 2)
    msg = f"{str(len_after).zfill(5)}/{str(len_before).zfill(5)} " \
          f"({filt_perc}%) shots were filtered due to poor quality"
    ancil.log(handler=log_handler, mode='info', file=gedi_path.name, msg=msg)
    return df
