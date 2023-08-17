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


def extract_data(directory, gedi_product='L2B', only_full_power=True, filter_month=(1, 12), subset_vector=None,
                 save_gpkg=True, dry_run=False):
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
    only_full_power: bool, optional
        Only keep shots from full power beams? Default is True.
    filter_month: tuple(int), optional
        Filter GEDI shots by month of the year? E.g. (6, 8) to only keep shots that were acquired between June 1st and
        August 31st of each year. Defaults to (1, 12), which keeps all shots of each year.
    subset_vector: str|Path or list(str|Path), optional
        Path or list of paths to vector files in a fiona supported format to subset the GEDI data spatially. Default is
        None, to keep all shots. Note that the basename of each vector file will be used in the output names, so it is
        recommended to give those files reasonable names beforehand!
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
    if isinstance(directory, str):
        directory = Path(directory)
    if isinstance(subset_vector, str):
        subset_vector = Path(subset_vector)
    if isinstance(subset_vector, list) and all(isinstance(x, str) for x in subset_vector):
        subset_vector = [Path(x) for x in subset_vector]
    
    log_handler, now = ancil.set_logging(directory)
    warnings.filterwarnings("ignore", category=ShapelyDeprecationWarning)  # https://gis.stackexchange.com/a/433423
    
    allowed = ['L2A', 'L2B']
    if gedi_product not in allowed:
        raise RuntimeError(f"Parameter 'gedi_product': expected to be one of {allowed}; got '{gedi_product}' instead.")
    
    spatial_subset = False
    if subset_vector is not None:
        out_dict = ancil.prepare_roi(vec=subset_vector)
        spatial_subset = True
    
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
            beams = [x for x in gedi.keys() if x.startswith('BEAM')]
            if only_full_power:
                beams = [x for x in beams if x in ['BEAM0101', 'BEAM0110', 'BEAM1000', 'BEAM1011']]
            
            # (3) Extract data and convert to Dataframe
            if gedi_product == 'L2A':
                df = pd.DataFrame(_from_l2a(gedi_file=gedi, beams=beams, acq_time=date, log_handler=log_handler))
            else:
                df = pd.DataFrame(_from_l2b(gedi_file=gedi, beams=beams, acq_time=date, log_handler=log_handler))
            
            # (4) Filter by quality flags
            df = filter_quality(df=df, log_handler=log_handler, gedi_path=fp)
            
            # (5) Convert to GeoDataFrame and set 'Shot Number' as index
            df['geometry'] = df.apply(lambda row: Point(row.longitude, row.latitude), axis=1)
            df = df.drop(columns=['latitude', 'longitude'])
            df = df.set_index('shot')
            gdf = gp.GeoDataFrame(df)
            gdf.crs = 'EPSG:4326'
            
            # (6) Subset spatially if any vector files were provided
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
            ancil.log(handler=log_handler, mode='exception', file=fp.name, msg=str(msg))
    
    ancil.close_logging(log_handler=log_handler)
    
    # (7) & (8)
    out_dir = directory / 'extracted'
    out_dir.mkdir(exist_ok=True)
    if spatial_subset:
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


def _from_l2a(gedi_file, beams, acq_time, log_handler):
    """
    Extracts general(*), quality(**) and analysis(***) related values from a GEDI L2A HDF5 file.
    
    (*)   `/<BEAM>/shot_number`, `/<BEAM>/lon_lowestmode`, `/<BEAM>/lat_lowestmode`
    (**)  `/<BEAM>/degrade_flag`, `/<BEAM>/quality_flag`, `/<BEAM>/sensitivity`
    (***) `/<BEAM>/rh[98]*100` (98th bin converted to cm)
    
    Parameters
    ----------
    gedi_file: h5py._hl.files.File
        A loaded GEDI L2A HDF5 file.
    beams: list(str)
        List of GEDI beams to extract values from.
    acq_time: datetime.datetime
        Acquisition date of the GEDI HDF5 file.
    log_handler: logging.Logger
        Current log handler.
    
    Returns
    -------
    out: dict
        Dictionary containing extracted values.
    """
    at, shot, lon, lat, degrade, quality, sensitivity, rh98 = ([] for i in range(9))
    for beam in beams:
        # General
        [shot.append(str(h)) for h in gedi_file[f'{beam}/shot_number'][()]]
        [lon.append(h) for h in gedi_file[f'{beam}/lon_lowestmode'][()]]
        [lat.append(h) for h in gedi_file[f'{beam}/lat_lowestmode'][()]]
        
        # Quality
        [degrade.append(h) for h in gedi_file[f'{beam}/degrade_flag'][()]]
        [quality.append(h) for h in gedi_file[f'{beam}/quality_flag'][()]]
        [sensitivity.append(h) for h in gedi_file[f'{beam}/sensitivity'][()]]
        
        # Analysis
        [rh98.append(round(h[98] * 100)) for h in gedi_file[f'{beam}/rh'][()]]
    
    [at.append(str(acq_time)) for s in range(len(shot))]
    out = {'shot': shot,
           'acq_time': at,
           'longitude': lon,
           'latitude': lat,
           'degrade_flag': degrade,
           'quality_flag': quality,
           'sensitivity': sensitivity,
           'rh98': rh98}
    del at, shot, lon, lat, degrade, quality, sensitivity, rh98
    return out


def _from_l2b(gedi_file, beams, acq_time, log_handler):
    """
    Extracts general(*), quality(**) and analysis(***) related values from a GEDI L2B HDF5 file.
    
    (*)   `/<BEAM>/shot_number`, `/<BEAM>/geolocation/lon_lowestmode`, `/<BEAM>/geolocation/lat_lowestmode`
    (**)  `/<BEAM>/geolocation/degrade_flag`, `/<BEAM>/l2b_quality_flag`, `/<BEAM>/sensitivity`
    (***) `/<BEAM>/cover`, `/<BEAM>/fhd_normal`, `/<BEAM>/pai`
    
    Parameters
    ----------
    gedi_file: h5py._hl.files.File
        A loaded GEDI L2B HDF5 file.
    beams: list(str)
        List of GEDI beams to extract values from.
    acq_time: datetime.datetime
        Acquisition date of the GEDI HDF5 file.
    log_handler: logging.Logger
        Current log handler.
    
    Returns
    -------
    out: dict
        Dictionary containing extracted values.
    """
    at, shot, lon, lat, degrade, quality, sensitivity, cover, fhd_index, pai, rh100 = ([] for i in range(11))
    for beam in beams:
        # General
        [shot.append(str(h)) for h in gedi_file[f'{beam}/shot_number'][()]]
        [lon.append(h) for h in gedi_file[f'{beam}/geolocation/lon_lowestmode'][()]]
        [lat.append(h) for h in gedi_file[f'{beam}/geolocation/lat_lowestmode'][()]]
        
        # Quality
        [degrade.append(h) for h in gedi_file[f'{beam}/geolocation/degrade_flag'][()]]
        [quality.append(h) for h in gedi_file[f'{beam}/l2b_quality_flag'][()]]
        [sensitivity.append(h) for h in gedi_file[f'{beam}/sensitivity'][()]]
        
        # Analysis
        [cover.append(h) for h in gedi_file[f'{beam}/cover'][()]]
        [fhd_index.append(h) for h in gedi_file[f'{beam}/fhd_normal'][()]]
        [pai.append(h) for h in gedi_file[f'{beam}/pai'][()]]
    
    [at.append(str(acq_time)) for s in range(len(shot))]
    out = {'shot': shot,
           'acq_time': at,
           'longitude': lon,
           'latitude': lat,
           'degrade_flag': degrade,
           'quality_flag': quality,
           'sensitivity': sensitivity,
           'tcc': cover,
           'fhdi': fhd_index,
           'pai': pai}
    del at, shot, lon, lat, degrade, quality, sensitivity, cover, fhd_index, pai
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
