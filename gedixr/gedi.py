from pathlib import Path
import re
import zipfile
from tqdm import tqdm
import h5py
import pandas as pd
import geopandas as gp
from shapely.geometry import Point

from typing import Optional
from tempfile import TemporaryDirectory
from datetime import datetime
from logging import Logger
from pandas import DataFrame
from geopandas import GeoDataFrame
from shapely import Polygon

import gedixr.ancillary as anc

ALLOWED_PRODUCTS = ['L2A', 'L2B']
PATTERN_L2A = '*GEDI02_A_*.h5'
PATTERN_L2B = '*GEDI02_B_*.h5'

FULL_POWER_BEAMS = ['BEAM0101', 'BEAM0110', 'BEAM1000', 'BEAM1011']
COVERAGE_BEAMS = ['BEAM0000', 'BEAM0001', 'BEAM0010', 'BEAM0011']

DEFAULT_VARIABLES = {'L2A': [('rh98', 'rh98')],
                     'L2B': [('tcc', 'cover'),
                             ('fhd', 'fhd_normal'),
                             ('pai', 'pai'),
                             ('rh100', 'rh100')]
                     }

_DEFAULT_BASE = {'L2A': [('shot', 'shot_number'),
                         ('latitude', 'lat_lowestmode'),
                         ('longitude', 'lon_lowestmode'),
                         ('elev', 'elev_lowestmode'),
                         ('elev_dem_tdx', 'digital_elevation_model'),
                         ('degrade_flag', 'degrade_flag'),
                         ('quality_flag', 'quality_flag'),
                         ('sensitivity', 'sensitivity'),
                         ('num_detectedmodes', 'num_detectedmodes')],
                 'L2B': [('shot', 'shot_number'),
                         ('latitude', 'geolocation/lat_lowestmode'),
                         ('longitude', 'geolocation/lon_lowestmode'),
                         ('elev', 'geolocation/elev_lowestmode'),
                         ('elev_dem_tdx', 'geolocation/digital_elevation_model'),
                         ('degrade_flag', 'geolocation/degrade_flag'),
                         ('quality_flag', 'l2b_quality_flag'),
                         ('sensitivity', 'sensitivity'),
                         ('num_detectedmodes', 'num_detectedmodes')]
                 }

N_ERRORS = 0


def extract_data(directory: str | Path,
                 gedi_product: str,
                 temp_unpack_zip: bool = False,
                 variables: Optional[list[tuple[str, str]]] = None,
                 beams: Optional[str| list[str]] = None,
                 filter_month: Optional[tuple[int, int]] = None,
                 subset_vector: Optional[str | Path | list[str | Path]] = None,
                 apply_quality_filter: bool = True
                 ) -> (GeoDataFrame | dict[str, dict[str, GeoDataFrame | Polygon]]):
    """
    Extracts data from GEDI L2A or L2B files in HDF5 format using the following
    steps:
    
    (1) Search a root directory recursively for GEDI L2A or L2B HDF5 files
    (2) OPTIONAL: Filter files by month of acquisition
    (3) Extract data from each file for specified beams and variables into a Dataframe
    (4) OPTIONAL: Filter out shots of poor quality
    (5) Convert Dataframe to GeoDataFrame including geometry column
    (6) OPTIONAL: Subset shots spatially using intersection via provided vector
        file or list of vector files
    (7) Save the result as a GeoParquet file or multiple files (one per
        provided vector file, if applicable)
    (8) Return a GeoDataFrame or dictionary of GeoDataFrame objects (one per provided
        vector file, if applicable)
    
    Parameters
    ----------
    directory: str or Path
        Root directory to recursively search for GEDI L2A/L2B files.
    gedi_product: str
        GEDI product type. Either 'L2A' or 'L2B'. Default is 'L2B'.
    temp_unpack_zip: bool, optional
        Unpack zip archives in temporary directories and use those to extract
        data from? Default is False. Use this option with caution, as it will
        create a temporary directory to decompress each zip archive found in the
        specified directory! The temporary directories will be deleted after the
        extraction process, but interruptions may cause them to remain on disk.
    variables: list of tuple of str, optional
        List of tuples containing the desired column name in the returned
        GeoDataFrame and the GEDI layer name to be extracted. Defaults to those
        retrieved by `gedixr.gedi.DEFAULT_VARIABLES['<gedi_product>']`.
    beams: str or list of str, optional
        Which GEDI beams to extract values from? Defaults to all beams (power and
        coverage beams). Use `'full'` or `'coverage'` for power or coverage beams,
        respectively. You can also provide a list of beam names, e.g.:
        `['BEAM0101', 'BEAM0110']`.
    filter_month: tuple(int), optional
        Filter GEDI shots by month of the year? E.g. (6, 8) to only keep shots
        that were acquired between June 1st and August 31st of each year.
        Defaults to (1, 12), which keeps all shots of each year.
    subset_vector: str or Path or list of str or Path, optional
        Path or list of paths to vector files in a fiona supported format to
        subset the GEDI data spatially. Default is None, to keep all shots.
        Note that the basename of each vector file will be used in the output
        names, so it is recommended to give those files reasonable names
        beforehand!
    apply_quality_filter: bool, optional
        Apply a basic quality filter to the GEDI data? Default is True. This basic
        filtering strategy will filter out shots with quality_flag != 1,
        degrade_flag != 0, num_detectedmodes > 1, and difference between detected
        elevation and DEM elevation < 100 m.
    
    Returns
    -------
    GeoDataFrame or dictionary
        In case of an output dictionary, these are the expected key, value pairs:
            {'<Vector Basename>': {'geo': Polygon, 'gdf': GeoDataFrame}}
    """
    if gedi_product not in ALLOWED_PRODUCTS:
        raise RuntimeError(f"Parameter 'gedi_product': expected to be one of "
                           f"{ALLOWED_PRODUCTS}; got {gedi_product} instead")
    
    directory = anc.to_pathlib(x=directory)
    subset_vector = anc.to_pathlib(x=subset_vector) if \
        (subset_vector is not None) else None
    log_handler, now = anc.set_logging(directory, gedi_product)
    out_dict = None
    if gedi_product == 'L2A':
        variables = DEFAULT_VARIABLES['L2A'] if variables is None else variables
        pattern = PATTERN_L2A
    else:
        variables = DEFAULT_VARIABLES['L2B'] if variables is None else variables
        pattern = PATTERN_L2B
    if beams is None:
        beams = FULL_POWER_BEAMS + COVERAGE_BEAMS
    elif beams == 'full':
        beams = FULL_POWER_BEAMS
    elif beams == 'coverage':
        beams = COVERAGE_BEAMS
    else:
        beams = beams
    if filter_month is None:
        filter_month = (1, 12)
    if subset_vector is not None:
        out_dict = anc.prepare_vec(vec=subset_vector)
    layers = _DEFAULT_BASE[gedi_product] + variables
    
    tmp_dirs = None
    try:
        # (1) Search for GEDI files
        if temp_unpack_zip:
            filepaths, tmp_dirs = _filepaths_from_zips(directory=directory,
                                                       pattern=pattern)
        else:
            filepaths = [p for p in directory.rglob('*') if p.is_file() and
                         p.match(pattern)]
        
        if len(filepaths) == 0:
            _cleanup_tmp_dirs(tmp_dirs)
            raise RuntimeError(f"No GEDI {gedi_product} files were found in "
                               f"{directory}.")
        
        gdf_list_no_spatial_subset = []
        for i, fp in enumerate(tqdm(filepaths)):
            # (2) Filter by month of acquisition
            date = _date_from_gedi_file(gedi_path=fp)
            if not filter_month[0] <= date.month <= filter_month[1]:
                msg = (f"Time of acquisition outside of filter range: "
                       f"month_min={filter_month[0]}, "
                       f"month_max={filter_month[1]}")
                anc.log(handler=log_handler, mode='info', file=fp.name, msg=msg)
                continue
            
            try:
                gedi = h5py.File(fp, 'r')
                
                # (3) Extract data for specified beams and variables
                df = pd.DataFrame(_from_file(gedi=gedi,
                                             gedi_fp=fp,
                                             gedi_product=gedi_product,
                                             beams=beams,
                                             layers=layers,
                                             acq_time=date,
                                             log_handler=log_handler))
                
                # (4) Filter by quality flags
                if apply_quality_filter:
                    df = filter_quality(df=df, log_handler=log_handler, gedi_path=fp)
                
                # (5) Convert to GeoDataFrame, set 'Shot Number' as index and convert
                # acquisition time to datetime
                df['geometry'] = df.apply(lambda row:
                                          Point(row.longitude, row.latitude),
                                          axis=1)
                df = df.drop(columns=['latitude', 'longitude'])
                gdf = gp.GeoDataFrame(df)
                gdf.set_crs(epsg=4326, inplace=True)
                gdf['acq_time'] = pd.to_datetime(gdf['acq_time'])
                
                # (6) Subset spatially if any vector files were provided
                if subset_vector is not None:
                    for k, v in out_dict.items():
                        gdf_sub = gdf[gdf.intersects(v['geo'])]
                        if not gdf_sub.empty:
                            if out_dict[k]['gdf'] is None:
                                out_dict[k]['gdf'] = gdf_sub
                            else:
                                gdf_cat = pd.concat([out_dict[k]['gdf'], gdf_sub])
                                out_dict[k]['gdf'] = gdf_cat
                        del gdf_sub
                else:
                    gdf_list_no_spatial_subset.append(gdf)
                
                gedi.close()
                del df, gdf
            except Exception as msg:
                anc.log(handler=log_handler, mode='exception', file=fp.name,
                        msg=str(msg))
                _error_counter()
        
        # (7) & (8)
        out_dir = directory / 'extracted'
        out_dir.mkdir(exist_ok=True)
        if subset_vector is not None:
            for vec_base, _dict in out_dict.items():
                if _dict['gdf'] is not None:
                    out_name = f'{now}__{gedi_product}__subset_{vec_base}.parquet'
                    _dict['gdf'].to_parquet(out_dir / out_name)
            return out_dict
        else:
            out = pd.concat(gdf_list_no_spatial_subset)
            out_name = f'{now}__{gedi_product}.parquet'
            out.to_parquet(out_dir / out_name)
            return out
    except Exception as msg:
        anc.log(handler=log_handler, mode='exception', msg=str(msg))
        _error_counter()
    finally:
        _cleanup_tmp_dirs(tmp_dirs)
        anc.close_logging(log_handler=log_handler)
        if N_ERRORS > 0:
            print(f"WARNING: {N_ERRORS} errors occurred during the extraction "
                  f"process. Please check the log file!")


def _error_counter():
    global N_ERRORS
    N_ERRORS += 1


def _date_from_gedi_file(gedi_path: Path) -> datetime:
    """Extract date string from GEDI filename and convert to datetime object."""
    date_str = re.search('[AB]_[0-9]{13}', gedi_path.name).group()
    date_str = date_str[2:]
    return datetime.strptime(date_str, '%Y%j%H%M%S')


def _cleanup_tmp_dirs(tmp_dirs: list[TemporaryDirectory]) -> None:
    """Cleanup temporary directories created during the extraction process."""
    if tmp_dirs is not None:
        for tmp_dir in tmp_dirs:
            tmp_dir.cleanup()


def _filepaths_from_zips(directory: Path,
                         pattern: str
                         ) -> (list[Path], list[TemporaryDirectory]):
    """Decompress zips to temp directories and find matching filepaths."""
    zip_files = [p for p in directory.rglob('*') if p.is_file() and
                 p.match('*.zip')]
    tmp_dirs = [TemporaryDirectory() for _ in zip_files]
    
    filepaths = []
    for zf, tmp_dir in zip(zip_files, tmp_dirs):
        tmp_dir_path = Path(tmp_dir.name)
        with zipfile.ZipFile(zf, 'r') as zip_ref:
            zip_ref.extractall(tmp_dir_path)
        match = [p for p in tmp_dir_path.rglob('*') if p.is_file() and
                 p.match(pattern)]
        filepaths.extend(match)
    return filepaths, tmp_dirs


def _from_file(gedi: h5py.File,
               gedi_fp: Path,
               gedi_product: str,
               beams: list[str],
               layers: list[tuple[str, str]],
               acq_time: datetime,
               log_handler: Logger
               ) -> dict:
    """
    Extracts values from a GEDI HDF5 file.
    
    Parameters
    ----------
    gedi: h5py.File
        A loaded GEDI HDF5 file.
    gedi_fp: Path
        Path to the current GEDI HDF5 file.
    gedi_product: str
        GEDI product type. Either 'L2A' or 'L2B'.
    beams: list of str
        List of GEDI beams to extract values from.
    layers: list of tuple of str
        List of tuples containing the desired column name in the returned
        GeoDataFrame and the respective GEDI layer name to be extracted.
    acq_time: datetime
        Acquisition time of the GEDI file.
    log_handler: Logger
        Current log handler.
    
    Returns
    -------
    out: dict
        Dictionary containing extracted values.
    """
    out = {}
    for beam in beams:
        if beam not in list(gedi.keys()):
            anc.log(handler=log_handler, mode='info', file=gedi_fp.name,
                    msg=f"{beam} not found in file")
            continue
        try:
            for k, v in layers:
                if v.startswith('rh') and gedi_product == 'L2A':
                    if k not in out:
                        out[k] = []
                    idx = int(v[2:])
                    out[k].extend([round(h_bin[idx] * 100) for h_bin in
                                   gedi[f'{beam}/rh'][()]])
                elif v == 'shot_number':
                    if k not in out:
                        out[k] = []
                    out[k].extend([str(h) for h in gedi[f'{beam}/{v}'][()]])
                else:
                    if k not in out:
                        out[k] = []
                    out[k].extend(gedi[f'{beam}/{v}'][()])
        except Exception as msg:
            anc.log(handler=log_handler, mode='exception',
                    file=f"{gedi_fp.name} ({beam})", msg=str(msg))
            _error_counter()
    out['acq_time'] = [(str(acq_time)) for _ in range(len(out['shot']))]
    return out


def filter_quality(df: DataFrame,
                   log_handler: Logger,
                   gedi_path: Path
                   ) -> DataFrame:
    """
    Filters a given pandas.Dataframe containing GEDI data using its quality
    flags.
    
    Parameters
    ----------
    df: Dataframe
        Dataframe containing data of the GEDI L2A/L2B file.
    log_handler: Logger
        Current log handler.
    gedi_path: Path
        Path to the current GEDI L2A/L2B file.
    
    Returns
    -------
    df: Dataframe
        The quality-filtered dataframe.
    """
    len_before = len(df)
    cond = (
            (df['quality_flag'].eq(1)) &  # already includes 'sensitivity' > 0.9
            (df['degrade_flag'].eq(0)) &
            (df['num_detectedmodes'].ge(1)) &
            (abs(df['elev'] - df['elev_dem_tdx']) < 100)
    )
    df = df.where(cond).dropna()
    df = df.drop(columns=['quality_flag', 'degrade_flag'])
    len_after = len_before - len(df)
    filt_perc = round((len_after / len_before) * 100, 2)
    msg = f"{str(len_after).zfill(5)}/{str(len_before).zfill(5)} " \
          f"({filt_perc}%) shots were filtered due to poor quality"
    anc.log(handler=log_handler, mode='info', file=gedi_path.name, msg=msg)
    return df
