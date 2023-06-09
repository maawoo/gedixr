from pathlib import Path
import logging
from datetime import datetime


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
    now = datetime.now().strftime('%Y%m%dT%H%M')
    log_local = logging.getLogger(__name__)
    log_local.setLevel(logging.DEBUG)
    
    log_file = directory.joinpath('log', f"{now}.log")
    log_file.parent.mkdir(exist_ok=True)
    
    fh = logging.FileHandler(filename=log_file, mode='a')
    log_local.addHandler(fh)
    form = logging.Formatter("[%(asctime)s] [%(levelname)8s] %(message)s")
    fh.setFormatter(form)
    
    return log_local


def log(handler, mode, file, msg, gedi_beam=None):
    """
    Format and handle log messages during processing.

    Parameters
    ----------
    handler: logging.Logger
        Log handler initiated with the function `ancillary.set_logging`.
    mode: str
        One of ['info', 'warning', 'error', 'exception']. Calls the respective logging helper function.
        E.g. `logging.info()`; https://docs.python.org/3/library/logging.html#logging.info
    file: str
        File that is being processed. E.g. a GEDI L2A/L2B file.
    msg: str or Exception
        The massage that should be logged.
    gedi_beam: str, optional
        GEDI beam name to provide additional information when processing GEDI L2A/L2B files.

    Returns
    -------
    None
    """
    if gedi_beam is None:
        message = f'{file} -- {msg}'
        message = message.format(file=file, msg=msg)
    else:
        message = f'{file} / {gedi_beam} -- {msg}'
        message = message.format(file=file, beam=gedi_beam, msg=msg)
    
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


def path_from_log_handler(directory, log_handler):
    """
    Create a new output path from `directory` and the basename of the file used by the current log handler.

    Parameters
    ----------
    directory: Path
        Path to a directory.
    log_handler:
        Current log handler.

    Returns
    -------
    out_base: Path
    """
    try:
        f = Path(log_handler.handlers[0].baseFilename).name
        out_base = directory.joinpath(f.replace('.log', ''))
    except IndexError:
        out_base = directory.joinpath(f"{datetime.now().strftime('%Y%m%dT%H%M')}")
    return out_base
