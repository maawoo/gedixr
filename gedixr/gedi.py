from pathlib import Path
import re
import warnings
from datetime import datetime
from tqdm import tqdm
import h5py
import pandas as pd
import geopandas as gp
from shapely.geometry import Point
from shapely.errors import ShapelyDeprecationWarning

from gedixr import log
import gedixr.ancillary as ancil


def extract_data(directory, gedi_product='L2B', filter_month=(1, 12), subset_vector=None, logger=None, save_gpkg=True,
                 dry_run=False):
    """
    Extracts data from GEDI L2A and L2B files using the following steps:
    (1) Searches for GEDI L2A or L2B files in a directory and its subdirectories.
    (2) Filters files by month of acquisition.
    (3) Extracts general, quality and analysis related information.
    (4) Filters out shots of poor quality.
    (5) Subsets shots spatially (intersection) via provided vector file or list of vector files.
    (6) Saves the results as a GeoPackage file or multiple files (one per provided vector file).

    Parameters
    ----------
    directory: str
        Directory containing GEDI L2B files (or subdirectories of).
    gedi_product: str
        GEDI product. Either 'L2A' or 'L2B' (default).
    filter_month: tuple(int), optional
        Filter GEDI shots by month of the year? E.g. (6, 8) to only keep shots that were acquired between June 1st and
        August 31st of each year. Defaults to (1, 12), which keeps all shots of each year.
    subset_vector: str or list(str)
        Path or list of paths to vector files in GeoJSON or Shapefile format. Note that the basename of each vector file
        will be used in the output names, so it is recommended to give those files reasonable names beforehand!
    logger: logging.Logger, optional
        Log handler initiated with the function `ancillary.set_logging`. Will be called automatically if `logger=None`.
    save_gpkg: bool, optional
        Save resulting GeoDataFrame as a Geopackage file in the directory specified with `gedi_dir`? Default is True.
    dry_run: bool, optional
        Will only print out how many GEDI files were found if set to True.

    Returns
    -------
    geopandas.geodataframe.GeoDataFrame or dictionary
        The key-value pairs in case of an output dictionary:
        {'vector_basename': {'geo': shapely.geometry.polygon.Polygon, 'gdf': geopandas.geodataframe.GeoDataFrame}}
    """
    directory = Path(directory)
    
    # https://gis.stackexchange.com/a/433423
    warnings.filterwarnings("ignore", category=ShapelyDeprecationWarning)
    
    spatial_subset = False
    if subset_vector is not None:
        out_dict = ancil.prepare_roi(vec=subset_vector)
        spatial_subset = True
    
    # TODO: Processing runs overwrite each other because the log handler persists!
    if logger is None:
        log_handler = log.set_logging(directory)
    else:
        log_handler = logger
    
    allowed = ['L2A', 'L2B']
    if gedi_product not in allowed:
        raise RuntimeError(f"Parameter 'gedi_product': expected to be one of {allowed}; got {gedi_product} instead")
    
    pattern = f'*GEDI02_{gedi_product[-1]}*.h5'
    filepaths = [p for p in directory.rglob('*') if p.is_file() and p.match(pattern)]
    
    if dry_run:
        print(f"{len(filepaths)} GEDI files were found to extract data from. Rerun without actvated 'dry_run'-flag ")
        return None
    
    gdf_list_no_spatial_subset = []
    for i, fp in enumerate(tqdm(filepaths)):
        
        # Filter by month of acquisition
        date = _date_from_gedi_file(gedi_path=fp)
        if not filter_month[0] <= date.month <= filter_month[1]:
            msg = f'Time of acquisition outside of filter range: month_min={filter_month[0]}, ' \
                  f'month_max={filter_month[1]}'
            log.log(handler=log_handler, mode='info', file=fp.name, msg=msg)
            continue
        
        try:
            gedi = h5py.File(fp, 'r')
            
            # Select only full power beams
            beams = [x for x in gedi.keys() if x in ['BEAM0101', 'BEAM0110', 'BEAM1000', 'BEAM1011']]
            
            # Extract GEDI layers
            if gedi_product == 'L2A':
                df = pd.DataFrame(_extract_gedi_l2a(gedi_file=gedi, beams=beams, acq_time=date,
                                                    log_handler=log_handler))
            else:
                df = pd.DataFrame(_extract_gedi_l2b(gedi_file=gedi, beams=beams, acq_time=date,
                                                    log_handler=log_handler))
            
            # Filter by quality flags
            df = _filter_gedi_quality(gedi_path=fp, df=df, log_handler=log_handler)
            
            # Convert to GeoDataFrame and set 'Shot Number' as index
            df['geometry'] = df.apply(lambda row: Point(row.Longitude, row.Latitude), axis=1)
            df = df.drop(columns=['Latitude', 'Longitude'])
            df = df.set_index('Shot Number')
            gdf = gp.GeoDataFrame(df)
            gdf.crs = 'EPSG:4326'
            
            # Subset spatially if any vector files were provided
            if spatial_subset:
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
            log.log(handler=log_handler, mode='exception', file=fp.name, msg=str(msg))
    
    out_gpkg_base = log.path_from_log_handler(directory=directory, log_handler=log_handler)
    if spatial_subset:
        if save_gpkg:
            for k, v in out_dict.items():
                if v['gdf'] is not None:
                    out_gpkg = out_gpkg_base.parent / (out_gpkg_base.name +
                                                       f'__{gedi_product}_' + '_subset_' + k + '.gpkg')
                    v['gdf'].to_file(out_gpkg, driver='GPKG')
        return out_dict
    else:
        out = pd.concat(gdf_list_no_spatial_subset)
        if save_gpkg:
            out_gpkg = out_gpkg_base.parent / (out_gpkg_base.name + f'__{gedi_product}' + '.gpkg')
            out.to_file(out_gpkg, driver='GPKG')
        return out


def _date_from_gedi_file(gedi_path):
    """
    Extracts the date from a GEDI L2A/L2B filepath and converts it to a datetime.datetime object.

    Parameters
    ----------
    gedi_path: Path
        Path to a GEDI L2A/L2B file.

    Returns
    -------
    date: datetime.datetime
    """
    date_str = re.search('[0-9]{13}', gedi_path.name).group()
    date = datetime.strptime(date_str, '%Y%j%H%M%S')
    return date


def _extract_gedi_l2a(gedi_file, beams, acq_time, log_handler):
    """
    Extracts general(*), quality(**) and analysis(***) related values from a GEDI L2A file.

    (*)   /<BEAM>/shot_number, /<BEAM>/lon_lowestmode, /<BEAM>/lat_lowestmode
    (**)  /<BEAM>/degrade_flag, /<BEAM>/quality_flag, /<BEAM>/sensitivity
    (***) /<BEAM>/rh[95]*100 (95th bin converted to cm), /<BEAM>/rh[98]*100 (98th bin converted to cm)

    Parameters
    ----------
    gedi_file: h5py._hl.files.File
        A loaded GEDI L2A file.
    beams: list(str)
        List of GEDI beams to extract values from.
    acq_time: datetime.datetime
        Acquisition date of the GEDI file.
    log_handler: logging.Logger
        Current log handler.

    Returns
    -------
    out: dict
        Dictionary containing extracted values.
    """
    try:
        at, shot, lon, lat, degrade, quality, sensitivity, rh95, rh98 = ([] for i in range(9))
        for beam in beams:
            # General & Quality related
            [shot.append(h) for h in gedi_file[f'{beam}/shot_number'][()]]
            [lon.append(h) for h in gedi_file[f'{beam}/lon_lowestmode'][()]]
            [lat.append(h) for h in gedi_file[f'{beam}/lat_lowestmode'][()]]
            [degrade.append(h) for h in gedi_file[f'{beam}/degrade_flag'][()]]
            [quality.append(h) for h in gedi_file[f'{beam}/quality_flag'][()]]
            [sensitivity.append(h) for h in gedi_file[f'{beam}/sensitivity'][()]]
            
            # Analysis related
            [rh95.append(round(h[95] * 100)) for h in gedi_file[f'{beam}/rh'][()]]
            [rh98.append(round(h[98] * 100)) for h in gedi_file[f'{beam}/rh'][()]]
        
        [at.append(str(acq_time)) for s in range(len(shot))]
        out = {'Shot Number': shot, 'Acquisition Time': at, 'Longitude': lon, 'Latitude': lat,
               'Degrade Flag': degrade, 'Quality Flag': quality, 'Sensitivity': sensitivity,
               'Relative Height bin95 (cm)': rh95, 'Relative Height bin98 (cm)': rh98}
        del at, shot, lon, lat, degrade, quality, sensitivity, rh95, rh98
        return out
    
    except Exception as msg:
        if "object 'shot_number' doesn't exist" in str(msg):
            # Avoid full error traceback for this exception in the log file
            msg = "KeyError: 'Unable to open object (object 'shot_number' doesn't exist)'"
            mode = 'error'
        else:
            mode = 'exception'
        log.log(handler=log_handler, mode=mode, file=gedi_file.name, gedi_beam=beam, msg=msg)


def _extract_gedi_l2b(gedi_file, beams, acq_time, log_handler):
    """
    Extracts general(*), quality(**) and analysis(***) related values from a GEDI L2B file.

    (*)   /<BEAM>/shot_number, /<BEAM>/geolocation/lon_lowestmode, /<BEAM>/geolocation/lat_lowestmode
    (**)  /<BEAM>/geolocation/degrade_flag, /<BEAM>/l2b_quality_flag, /<BEAM>/sensitivity
    (***) /<BEAM>/cover, /<BEAM>/fhd_normal, /<BEAM>/pai

    Parameters
    ----------
    gedi_file: h5py._hl.files.File
        A loaded GEDI L2B file.
    beams: list(str)
        List of GEDI beams to extract values from.
    acq_time: datetime.datetime
        Acquisition date of the GEDI file.
    log_handler: logging.Logger
        Current log handler.

    Returns
    -------
    out: dict
        Dictionary containing extracted values.
    """
    try:
        at, shot, lon, lat, degrade, quality, sensitivity, cover, fhd_index, pai, rh100 = ([] for i in range(11))
        for beam in beams:
            # General & Quality related
            [shot.append(h) for h in gedi_file[f'{beam}/shot_number'][()]]
            [lon.append(h) for h in gedi_file[f'{beam}/geolocation/lon_lowestmode'][()]]
            [lat.append(h) for h in gedi_file[f'{beam}/geolocation/lat_lowestmode'][()]]
            [degrade.append(h) for h in gedi_file[f'{beam}/geolocation/degrade_flag'][()]]
            [quality.append(h) for h in gedi_file[f'{beam}/l2b_quality_flag'][()]]
            [sensitivity.append(h) for h in gedi_file[f'{beam}/sensitivity'][()]]
            
            # Analysis related
            [cover.append(h) for h in gedi_file[f'{beam}/cover'][()]]
            [fhd_index.append(h) for h in gedi_file[f'{beam}/fhd_normal'][()]]
            [pai.append(h) for h in gedi_file[f'{beam}/pai'][()]]
        
        [at.append(str(acq_time)) for s in range(len(shot))]
        out = {'Shot Number': shot, 'Acquisition Time': at, 'Longitude': lon, 'Latitude': lat,
               'Degrade Flag': degrade, 'Quality Flag': quality, 'Sensitivity': sensitivity,
               'Total Canopy Cover': cover, 'Foliage Height Diversity Index': fhd_index, 'Total Plant Area Index': pai}
        del at, shot, lon, lat, degrade, quality, sensitivity, cover, fhd_index, pai
        return out
    
    except Exception as msg:
        if "object 'shot_number' doesn't exist" in str(msg):
            # Avoid full error traceback for this exception in the log file
            msg = "KeyError: 'Unable to open object (object 'shot_number' doesn't exist)'"
            mode = 'error'
        else:
            mode = 'exception'
        log.log(handler=log_handler, mode=mode, file=gedi_file.name, gedi_beam=beam, msg=msg)


def _filter_gedi_quality(gedi_path, df, log_handler):
    """
    Filters a given pandas.Dataframe containing GEDI data using its quality flags. The values used here have been
    adopted from the official GEDI L2A/L2B tutorials:
    https://git.earthdata.nasa.gov/projects/LPDUR/repos/gedi-v2-tutorials/browse

    Parameters
    ----------
    gedi_path: Path
        Path to a GEDI L2A/L2B file.
    df: :obj:`pandas.Dataframe`
        Dataframe containing data of the GEDI L2A/L2B file.
    log_handler: logging.Logger
        Current log handler.

    Returns
    -------
    pandas.Dataframe
    """
    len_before = len(df)
    df = df.where(df['Quality Flag'].ne(0))
    df = df.where(df['Degrade Flag'] < 1)
    df = df.where(df['Sensitivity'] > 0.95)
    df = df.dropna()
    df = df.drop(columns=['Quality Flag', 'Degrade Flag', 'Sensitivity'])
    len_after = len_before - len(df)
    filt_perc = round((len_after / len_before) * 100, 2)
    msg = f"{str(len_after).zfill(5)}/{str(len_before).zfill(5)} " \
          f"({filt_perc}%) shots were filtered due to poor quality"
    log.log(handler=log_handler, mode='info', file=gedi_path.name, msg=msg)
    return df
