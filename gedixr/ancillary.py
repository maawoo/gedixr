from pathlib import Path
import logging
from datetime import datetime
import geopandas as gp

from typing import Optional
from shapely import Polygon


def set_logging(directory: Path,
                gedi_product: str
                ) -> (logging.Logger, str):
    """
    Set logging for the current process.
    
    Parameters
    ----------
    directory: Path
        Directory in which to store logfiles. Will create a subdirectory called
        '<directory>/log'.
    gedi_product: str
        One of ['L2A', 'L2B']. Used to name the log file.
    
    Returns
    -------
    log_local: logging.Logger
        The log handler for the current process.
    """
    now = datetime.now().strftime('%Y%m%dT%H%M%S')
    
    log_local = logging.getLogger(__name__)
    log_local.setLevel(logging.DEBUG)
    
    log_file = directory.joinpath('log', f"{now}__{gedi_product}.log")
    log_file.parent.mkdir(exist_ok=True)
    
    fh = logging.FileHandler(filename=log_file, mode='a')
    form = logging.Formatter("[%(asctime)s] [%(levelname)8s] %(message)s")
    fh.setFormatter(form)
    log_local.addHandler(fh)
    
    return log_local, now


def log(handler: logging.Logger,
        mode: str,
        msg: str,
        file: Optional[str] = None
        ) -> None:
    """
    Format and handle log messages during processing.
    
    Parameters
    ----------
    handler: logging.Logger
        Log handler initiated with the function `set_logging`.
    mode: str
        One of ['info', 'warning', 'error', 'exception']. Calls the respective
        logging helper function. E.g. `logging.info()`:
        https://docs.python.org/3/library/logging.html#logging.info
    msg: str or Exception
        The massage that should be logged.
    file: str, optional
        File that is being processed. E.g. a GEDI L2A/L2B file.
    
    Returns
    -------
    None
    """
    if file is not None:
        message = f'{file} -- {msg}'
        message = message.format(file=file, msg=msg)
    else:
        message = msg
    
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


def close_logging(log_handler: logging.Logger) -> None:
    """
    Close logging for the current process. This is necessary to avoid appending
    to the previous log file when executing the same process repeatedly.
    
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


def prepare_roi(vec: Path | list[Path]
                ) -> dict[str, dict[str, Polygon | None]]:
    """
    Prepares a vector file or list of vector files for spatial subsetting by
    extracting the geometry of each vector file and storing it in a dictionary.
    
    Parameters
    ----------
    vec: Path or list of Path
        Path or list of paths to vector files in a fiona supported format. If a
        multi-feature polygon is detected, the first feature will be used for
        subsetting.
    
    Returns
    -------
    out: dict
        Dictionary with key-value pairs:
        {'<Vector Basename>': {'geo': Polygon,
                               'gdf': None}}
    """
    if not isinstance(vec, list):
        vec = [vec]
    
    out = {}
    for v in vec:
        roi = gp.GeoDataFrame.from_file(str(v))
        if not roi.crs == 'EPSG:4326':
            roi = roi.to_crs('EPSG:4326')
        if len(roi) > 1:
            print("WARNING: Multi-feature polygon detected. Only the first "
                  "feature will be used to subset the GEDI data!")
        v_basename = Path(v).name.split('.')[0]
        out[v_basename] = {'geo': roi.geometry[0], 'gdf': None}
    
    return out


def to_pathlib(x: str | list[str]) -> Path | list[Path]:
    """
    Convert string(s) to Path object(s).
    
    Parameters
    ----------
    x: str or list of str
        String or list of strings to be converted to Path objects.
    
    Returns
    -------
    Path or list of Path
    """
    if (isinstance(x, Path) or isinstance(x, list) and
            all([isinstance(i, Path) for i in x])):
        return x
    elif isinstance(x, str):
        return Path(x)
    elif isinstance(x, list) and any([isinstance(i, str) for i in x]):
        return [Path(i) for i in x]
    else:
        raise TypeError('Input must be a string or list of strings.')
