from pathlib import Path
import tempfile
import zipfile
import logging
from tqdm import tqdm
import h5py
import pandas as pd
import geopandas as gp
from shapely.geometry import Point

import gedixr.ancillary as ancil

ALLOWED_PRODUCTS = ['L2A', 'L2B']
PATTERN_L2A = '*GEDI02_A_*.h5'
PATTERN_L2B = '*GEDI02_B_*.h5'

FULL_POWER_BEAMS = ['BEAM0101', 'BEAM0110', 'BEAM1000', 'BEAM1011']

VARIABLES_BASIC_L2A = [('shot', 'shot_number'),
                       ('latitude', 'lat_lowestmode'),
                       ('longitude', 'lon_lowestmode'),
                       ('degrade_flag', 'degrade_flag'),
                       ('quality_flag', 'quality_flag'),
                       ('sensitivity', 'sensitivity'),
                       ('rh95', 'rh95'),
                       ('rh98', 'rh98')]

VARIABLES_BASIC_L2B = [('shot', 'shot_number'),
                       ('latitude', 'geolocation/lat_lowestmode'),
                       ('longitude', 'geolocation/lon_lowestmode'),
                       ('degrade_flag', 'geolocation/degrade_flag'),
                       ('quality_flag', 'l2b_quality_flag'),
                       ('sensitivity', 'sensitivity'),
                       ('tcc', 'cover'),
                       ('fhd', 'fhd_normal'),
                       ('pai', 'pai'),
                       ('rh100', 'rh100')]


def extract_data(directory, temp_unpack_zip=False, gedi_product='L2B', filter_month=(1, 12), variables=None, beams=None,
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
    temp_unpack_zip: bool, optional
        Unpack zip archives in temporary directories and use those to extract data from? Default is False.
        Use this option with caution, as it will create a temporary directory to decompress each zip archive found in
        the specified directory! The temporary directories will be deleted after the extraction process, but interruptions
        may cause them to remain on the disk.
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
        List of tuples containing the desired column name in the returned GeoDataFrame and the respective GEDI layer name.
        Defaults to `gedixr.gedi.VARIABLES_BASIC_L2A` for L2A products and `gedixr.gedi.VARIABLES_BASIC_L2B` for L2B products.
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
        out_dict = ancil.prepare_roi(vec=subset_vector)
    
    if beams is None:
        beams = FULL_POWER_BEAMS
    
    if variables is None:
        if gedi_product == 'L2A':
            variables = VARIABLES_BASIC_L2A
        else:
            variables = VARIABLES_BASIC_L2B
            
    if gedi_product == 'L2A':
        pattern = PATTERN_L2A
    else:
        pattern = PATTERN_L2B
    
    tmp_dirs = None
    try:
        # (1) Search for GEDI files
        if temp_unpack_zip:
            filepaths, tmp_dirs = _filepaths_from_zips(directory=directory, pattern=pattern)
        else:
            filepaths = [p for p in directory.rglob('*') if p.is_file() and p.match(pattern)]
    
        if dry_run:
            print(f"{len(filepaths)} GEDI {gedi_product} files were found to extract data from. "
                  f"Rerun without activated 'dry_run'-flag to extract data.")
            _cleanup_tmp_dirs(tmp_dirs)
            ancil.close_logging(log_handler=log_handler)
            return None
        if len(filepaths) == 0:
            _cleanup_tmp_dirs(tmp_dirs)
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
        _cleanup_tmp_dirs(tmp_dirs)
        ancil.close_logging(log_handler=log_handler)
        if n_err > 0:
            print(f"WARNING: {n_err} errors occurred during the extraction process. Please check the log file!")


def _cleanup_tmp_dirs(tmp_dirs):
    """Cleanup temporary directories created during the extraction process."""
    if tmp_dirs is not None:
        for tmp_dir in tmp_dirs:
            tmp_dir.cleanup()


def _filepaths_from_zips(directory, pattern):
    """Decompress zip archives in temporary directories and return filepaths matching the given pattern."""
    zip_files = [p for p in directory.rglob('*') if p.is_file() and p.match('*.zip')]
    tmp_dirs = [tempfile.TemporaryDirectory() for _ in zip_files]
    
    filepaths = []
    for zf, tmp_dir in zip(zip_files, tmp_dirs):
        tmp_dir_path = Path(tmp_dir.name)
        with zipfile.ZipFile(zf, 'r') as zip_ref:
            zip_ref.extractall(tmp_dir_path)
        match = [p for p in tmp_dir_path.rglob('*') if p.is_file() and p.match(pattern)]
        filepaths.extend(match)
    return filepaths, tmp_dirs


def _from_file(gedi_file, beams, variables, acq_time='Acquisition Time'):
    """
    Extracts values from a GEDI HDF5 file.
    
    Parameters
    ----------
    gedi_file: h5py._hl.files.File
        A loaded GEDI HDF5 file.
    beams: list(str)
        List of GEDI beams to extract values from.
    variables: list(tuple(str)), optional
        List of tuples containing the desired column name in the returned GeoDataFrame and the respective GEDI layer name.
        Defaults to `gedixr.gedi.VARIABLES_BASIC_L2A` for L2A products and `gedixr.gedi.VARIABLES_BASIC_L2B` for L2B products.
    acq_time: str
        Name of the GEDI layer containing the acquisition time.
    
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
    
    out['acq_time'] = [(str(acq_time)) for _ in range(len(out['shot']))]
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
