from pathlib import Path
import re
import logging
from datetime import datetime
import geopandas as gp


def set_logging(directory):
    """
    Set logging for the current process.

    Parameters
    ----------
    directory: Path
        Directory in which to store logfiles. Will create a subdirectory called '<directory>/log'.

    Returns
    -------
    log_local: logging.Logger
        The log handler for the current process.
    """
    now = datetime.now().strftime('%Y%m%dT%H%M%S')
    
    log_local = logging.getLogger(__name__)
    log_local.setLevel(logging.DEBUG)
    
    log_file = directory.joinpath('log', f"{now}.log")
    log_file.parent.mkdir(exist_ok=True)
    
    fh = logging.FileHandler(filename=log_file, mode='a')
    form = logging.Formatter("[%(asctime)s] [%(levelname)8s] %(message)s")
    fh.setFormatter(form)
    log_local.addHandler(fh)
    
    return log_local, now


def log(handler, mode, file, msg):
    """
    Format and handle log messages during processing.

    Parameters
    ----------
    handler: logging.Logger
        Log handler initiated with the function `set_logging`.
    mode: str
        One of ['info', 'warning', 'error', 'exception']. Calls the respective logging helper function.
        E.g. `logging.info()`; https://docs.python.org/3/library/logging.html#logging.info
    file: str
        File that is being processed. E.g. a GEDI L2A/L2B file.
    msg: str or Exception
        The massage that should be logged.

    Returns
    -------
    None
    """
    message = f'{file} -- {msg}'
    message = message.format(file=file, msg=msg)
    
    if mode == 'info':
        handler.info(message)
    elif mode == 'error':
        handler.error(message, exc_info=False)
    elif mode == 'warning':
        handler.warning(message)
    elif mode == 'exception':
        handler.exception(message)
    else:
        raise RuntimeError('log mode {} is not supported'.format(mode))


def close_logging(log_handler):
    """
    Close logging for the current process. This is necessary to avoid appending to the previous log file when
    executing the same process repeatedly.
    
    Parameters
    ----------
    log_handler: logging.Logger
        Log handler initiated with the function `set_logging`.

    Returns
    -------
    None
    """
    for handler in log_handler.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            handler.close()
            log_handler.removeHandler(handler)


def prepare_roi(vec):
    """
    Prepares a vector file or list of vector files for spatial subsetting by extracting the geometry of each vector file
    and storing it in a dictionary.

    Parameters
    ----------
    vec: Path or list(Path)
        Path or list of paths to vector files in a fiona supported format. If a multi-feature polygon is detected,
        the first feature will be used for subsetting.

    Returns
    -------
    out: dict
        Dictionary with key-value pairs:
        {'<Vector Basename>': {'geo': shapely.geometry.polygon.Polygon,
                               'gdf': None}}
    """
    if not isinstance(vec, list):
        vec = [vec]
    
    out = {}
    for v in vec:
        roi = gp.GeoDataFrame.from_file(v)
        if not roi.crs == 'EPSG:4326':
            roi = roi.to_crs('EPSG:4326')
        if len(roi) > 1:
            print('WARNING: Multi-feature polygon detected. Only the first feature will be used to subset the GEDI '
                  'data!')
        v_basename = Path(v).name.split('.')[0]
        out[v_basename] = {'geo': roi.geometry[0], 'gdf': None}
    
    return out


def date_from_gedi_file(gedi_path):
    """
    Extracts the date from a GEDI L2A/L2B HDF5 file and converts it to a datetime.datetime object.

    Parameters
    ----------
    gedi_path: Path
        Path to a GEDI L2A/L2B HDF5 file.

    Returns
    -------
    date: datetime.datetime
    """
    date_str = re.search('[AB]_[0-9]{13}', gedi_path.name).group()
    date_str = date_str[2:]
    date = datetime.strptime(date_str, '%Y%j%H%M%S')
    return date
