import logging
import platform
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import geopandas as gp
from shapely import Polygon


class ErrorTracker:
    def __init__(self):
        self.count = 0
    
    def reset(self):
        self.count = 0
    
    def increment(self):
        self.count += 1

error_tracker = ErrorTracker()


def set_logging(
    directory: Path,
    gedi_product: str,
    product_version: str
) -> tuple[logging.Logger, str]:
    """
    Set logging for the current process.
    
    Parameters
    ----------
    directory: Path
        Directory in which to store logfiles. Will create a subdirectory called
        '<directory>/log'.
    gedi_product: str
        One of ['L2A', 'L2B']. Used to name the log file.
    product_version: str
        One of ['V002', 'V003']. Used to name the log file.
    
    Returns
    -------
    log_local: logging.Logger
        The log handler for the current process.
    """
    now = datetime.now().strftime('%Y%m%dT%H%M%S')  # noqa: DTZ005
    
    log_local = logging.getLogger(__name__)
    log_local.setLevel(logging.DEBUG)
    
    log_file = directory.joinpath('log', f"{now}_{gedi_product}-{product_version}.log")
    log_file.parent.mkdir(exist_ok=True)
    
    fh = logging.FileHandler(filename=log_file, mode='a')
    form = logging.Formatter("[%(asctime)s] [%(levelname)8s] %(message)s")
    fh.setFormatter(form)
    log_local.addHandler(fh)
    return log_local, now


def log(
    handler: logging.Logger,
    mode: str,
    msg: str,
    file: str | None = None
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
        raise RuntimeError(f'log mode {mode} is not supported')


def initialize_log(
    handler: logging.Logger,
    gedi_product: str,
    product_version: str,
    variables: list[str],
    beams: list[str],
    filter_month: int | None,
    subset_vector: Path | list[Path] | None,
    apply_quality_filter: bool
) -> None:
    """
    Initialize logging for the current process.
    
    Parameters
    ----------
    handler: logging.Logger
        Log handler initiated with the function `set_logging`.
    gedi_product: str
        One of ['L2A', 'L2B'].
    product_version: str
        One of ['V002', 'V003'].
    variables: list of str
        List of variables to extract from the GEDI L2A/L2B files.
    beams: list of str
        List of beams to extract from the GEDI L2A/L2B files.
    filter_month: int or None
        Month to filter the GEDI L2A/L2B files by. If None, no filtering is applied.
    subset_vector: Path or list of Path or None
        Path or list of paths to vector files in a fiona supported format. If None, no subsetting 
        is applied.
    apply_quality_filter: bool
        Whether to apply the quality filter to the GEDI L2A/L2B files.
    """
    log(handler=handler, mode='info',
        msg=f"System information: {platform.platform()} {platform.processor()}, "
            f"Python {platform.python_version()}, "
            f"gedixr {version('gedixr')}, "
            f"pandas {version('pandas')}, "
            f"geopandas {version('geopandas')}")
    log(handler=handler, mode='info',
        msg=f"Starting GEDI {gedi_product}-{product_version} data extraction using parameters: "
            f"variables={variables}, beams={beams}, "
            f"filter_month={filter_month}, "
            f"subset_vector={subset_vector}, "
            f"apply_quality_filter={apply_quality_filter}")


def close_logging(log_handler: logging.Logger) -> None:
    """
    Close logging for the current process. This is necessary to avoid appending
    to the previous log file when executing the same process repeatedly.
    
    Parameters
    ----------
    log_handler: logging.Logger
        Log handler initiated with the function `set_logging`.
    """
    for handler in log_handler.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            handler.close()
            log_handler.removeHandler(handler)


def prepare_vec(vec: Path | list[Path]) -> dict[str, dict[str, Polygon | None]]:
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
    out = {}
    if not isinstance(vec, list):
        vec = [vec]
    for fp in vec:
        key_base = Path(fp).name.split('.')[0]
        gdf = gp.GeoDataFrame.from_file(str(fp))
        if gdf.crs != 'EPSG:4326':
            gdf = gdf.to_crs('EPSG:4326')
        if len(gdf) > 1:
            for i, row in gdf.iterrows():
                key = f"{key_base}_{i}"
                out[key] = {'geo': row.geometry, 'gdf': None}
        else:
            out[key_base] = {'geo': gdf.iloc[0].geometry, 'gdf': None}
    return out


def to_pathlib(x: str | list[str] | list[Path]) -> Path | list[Path]:
    """Convert string(s) to Path object(s)."""
    if (isinstance(x, Path) or isinstance(x, list) and
            all(isinstance(i, Path) for i in x)):
        return x
    elif isinstance(x, str):
        return Path(x)
    elif isinstance(x, list) and any(isinstance(i, str) for i in x):
        return [Path(i) for i in x]
    else:
        raise TypeError('Input must be a string or list of strings.')
