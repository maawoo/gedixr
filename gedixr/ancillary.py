from pathlib import Path
import re
from datetime import datetime
import geopandas as gp


def prepare_roi(vec):
    """
    Prepares a vector file or list of vector files for spatial subsetting by extracting the geometry of each vector file
    and storing it in a dictionary.

    Parameters
    ----------
    vec: str or list(str)
        Path or list of paths to vector files in a fiona supported format. If a multi-feature polygon is detected,
        the first feature will be used for subsetting.

    Returns
    -------
    out: dict
        Dictionary with key-value pairs:
        {'<Vector Basename>': {'geo': shapely.geometry.polygon.Polygon,
                               'gdf': None}}
    """
    if isinstance(vec, str):
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
