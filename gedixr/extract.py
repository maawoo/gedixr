import re
from datetime import datetime
from logging import Logger
from pathlib import Path

import geopandas as gp
import h5py
import pandas as pd
from geopandas import GeoDataFrame
from pandas import DataFrame
from shapely import Polygon
from shapely.geometry import Point
from tqdm import tqdm

import gedixr.ancillary as anc
import gedixr.constants as con


def extract_data(
    directory: str | Path,
    gedi_product: str,
    product_version: str = 'V003',
    variables: list[tuple[str, str]] | None = None,
    beams: str | list[str] | None = None,
    filter_month: tuple[int, int] | None = None,
    subset_vector: str | Path | list[str | Path] | None = None,
    apply_quality_filter: bool = True
) -> tuple[GeoDataFrame | dict[str, dict[str, GeoDataFrame | Polygon] | Path], Path | None]:
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
    product_version: str
        GEDI product version. Either 'V002' or 'V003'. Default is 'V003'.
    variables: list of tuple of str, optional
        List of tuples containing the desired column name in the returned
        GeoDataFrame and the GEDI layer name to be extracted. Defaults to those
        retrieved by `gedixr.constants.DEFAULT_VARIABLES['<gedi_product>']`.
    beams: str or list of str, optional
        Which GEDI beams to extract values from? Defaults to all beams (power and
        coverage beams). Use `'power'` or `'coverage'` for power or coverage beams,
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
            `{'<Vector Basename>': {'geo': Polygon, 'gdf': GeoDataFrame, 'path': Path}}`
            where 'geo' is the geometry of the vector file, 'gdf' is the extracted
            GeoDataFrame for that geometry, and 'path' is the path to the output
            GeoParquet file.
        If no vector files were provided, a single GeoDataFrame is returned.
    out_path: Path or None
        In case no vector files were provided, the path to the output GeoParquet
        file is returned. Otherwise, None is returned as the output paths are
        included in the output dictionary.
    """
    if gedi_product not in con.ALLOWED_PRODUCTS:
        raise RuntimeError(f"Parameter 'gedi_product': expected to be one of "
                           f"{con.ALLOWED_PRODUCTS}; got {gedi_product} instead")
    if product_version not in con.PRODUCT_MAPPING[gedi_product]:
        raise RuntimeError(f"Parameter 'product_version': expected to be one of "
                           f"{list(con.PRODUCT_MAPPING[gedi_product].keys())}; got {product_version} instead")

    directory = anc.to_pathlib(x=directory)
    subset_vector = anc.to_pathlib(x=subset_vector) if \
        (subset_vector is not None) else None
    log_handler, now = anc.set_logging(directory, gedi_product, product_version)
    anc.initialize_log(handler=log_handler,
                       gedi_product=gedi_product,
                       product_version=product_version,
                       variables=variables,
                       beams=beams,
                       filter_month=filter_month,
                       subset_vector=subset_vector,
                       apply_quality_filter=apply_quality_filter)
    
    anc.error_tracker.reset() 
    out_dict = None
    if gedi_product == 'L2A':
        variables = con.DEFAULT_VARIABLES['L2A'] if variables is None else variables
        pattern = con.PATTERN_L2A
    else:
        variables = con.DEFAULT_VARIABLES['L2B'] if variables is None else variables
        pattern = con.PATTERN_L2B
    if beams is None:
        beams = con.POWER_BEAMS + con.COVERAGE_BEAMS
    elif beams == 'power':
        beams = con.POWER_BEAMS
    elif beams == 'coverage':
        beams = con.COVERAGE_BEAMS
    else:
        beams = beams  # noqa: PLW0127
    if filter_month is None:
        filter_month = (1, 12)
    if subset_vector is not None:
        out_dict = anc.prepare_vec(vec=subset_vector)
    
    # Get the base variables for the specified product and version, applying overrides for V003
    layers = _get_base_variables(gedi_product, product_version) + variables

    try:
        # (1) Search for GEDI files
        filepaths = [p for p in directory.rglob('*') if p.is_file() and p.match(pattern)]
        filepaths = [p for p in filepaths if _check_product_version(p, product_version.upper())]

        if len(filepaths) == 0:
            raise RuntimeError(f"No GEDI {gedi_product}-{product_version} files were found in "
                               f"{directory}.")
        
        gdf_list_no_spatial_subset = []
        for i, fp in enumerate(tqdm(filepaths)):
            # (2) Filter by month of acquisition
            date = _date_from_gedi_file(gedi_path=fp)
            if filter_month[0] > filter_month[1]:
                filter_month = (filter_month[1], filter_month[0])
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
                                             product_version=product_version,
                                             beams=beams,
                                             layers=layers,
                                             acq_time=date,
                                             log_handler=log_handler))
                
                # (4) Filter by quality flags
                if apply_quality_filter:
                    df = _filter_quality(df=df, log_handler=log_handler, gedi_path=fp)
                
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
                    if not gdf.empty:
                        gdf_list_no_spatial_subset.append(gdf)
                
                gedi.close()
                del df, gdf
            except Exception as msg:  # noqa: BLE001
                anc.log(handler=log_handler, mode='exception', file=fp.name,
                        msg=str(msg))
                anc.error_tracker.increment()
        
        # (7) & (8)
        flt = 1 if apply_quality_filter else 0
        out_dir = directory / 'extracted'
        out_dir.mkdir(exist_ok=True)
        if subset_vector is not None:
            for k, v in out_dict.items():
                v['path'] = None
                if v['gdf'] is not None:
                    out_path = out_dir.joinpath(f'{now}_{gedi_product}-{product_version}_{flt}_{k}.parquet')
                    v['gdf'].to_parquet(out_path)
                    v['path'] = out_path
            return out_dict, None
        else:
            out_path = None
            # make sure that gdf's in list are not all empty 
            if gdf_list_no_spatial_subset:
                out = pd.concat(gdf_list_no_spatial_subset)
                out_path = out_dir.joinpath(f'{now}_{gedi_product}-{product_version}_{flt}.parquet')
                out.to_parquet(out_path)
            else:
                anc.log(handler=log_handler, mode='info',
                        msg="No GEDI shots passed the filtering criteria; "
                            "no output file created.")
                out = GeoDataFrame()
            return out, out_path
    except Exception as msg:  # noqa: BLE001
        anc.log(handler=log_handler, mode='exception', msg=str(msg))
        anc.error_tracker.increment()
    finally:
        anc.close_logging(log_handler=log_handler)
        error_count = anc.error_tracker.count
        if error_count > 0:
            print(f"WARNING: {error_count} errors occurred during the extraction "
                  f"process. Please check the log file!")


def _check_product_version(path: Path, version: str) -> bool:
    """ Checks if a given GEDI file path corresponds to the specified product version."""
    name = path.name
    regex = re.compile(rf'[_\.]?{re.escape(version)}.*\.h5$', re.IGNORECASE)
    return regex.search(name) is not None


def _get_base_variables(
    product: str,
    version: str,
    base_dict: dict[str, list[tuple[str, str]]] = con.DEFAULT_BASE,
    override_dict: dict[str, dict[str, str]] = con.DEFAULT_BASE_V003_CHANGES,
) -> list[tuple[str, str]]:
    """ Returns the base variables for a given product and version, applying overrides for V003 if necessary."""
    base_vars = base_dict[product]

    if version == 'V002':
        return base_vars
    if version == 'V003':
        overrides = override_dict.get(product, {})
        if not overrides:
            return base_vars

        # Build a mapping from output_name -> (output_name, hdf_path)
        var_map = {name: (name, path) for name, path in base_vars}

        # Apply overrides: replace hdf_path for matching output_name
        for name, new_path in overrides.items():
            if name in var_map:
                var_map[name] = (name, new_path)
        
        return list(var_map.values())
    raise ValueError(f"Unsupported version: {version}")


def _date_from_gedi_file(gedi_path: Path) -> datetime:
    """Extract date string from GEDI filename and convert to datetime object."""
    date_str = re.search('[AB]_[0-9]{13}', gedi_path.name).group()
    date_str = date_str[2:]
    return datetime.strptime(date_str, '%Y%j%H%M%S')  # noqa: DTZ007


def _from_file(
    gedi: h5py.File,
    gedi_fp: Path,
    gedi_product: str,
    product_version: str,
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
    product_version: str
        GEDI product version. Either 'V002' or 'V003'.
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
    out: dict of list
        Dictionary containing the extracted values for the specified beams and variables. 
        The keys are the desired column names in the returned GeoDataFrame, and the values are 
        lists of the extracted values for each shot. The length of each list corresponds to the 
        number of shots
    """
    out: dict[str, list] = {}
    for beam in beams:
        if beam not in list(gedi.keys()) or "shot_number" not in gedi[beam]:
            anc.log(handler=log_handler, mode="info", file=gedi_fp.name, msg=f"{beam} not found in file")
            continue
        
        # Extract shot numbers first to determine the number of shots (n) for the current beam, which is
        # needed to handle potential errors in the extraction of other variables and keep column lengths aligned.
        try:
            shot_raw = gedi[f"{beam}/shot_number"][()]
            n = len(shot_raw)
        except Exception as msg:  # noqa: BLE001
            anc.log(handler=log_handler, mode="exception", file=f"{gedi_fp.name} ({beam})", msg=str(msg))
            anc.error_tracker.increment()
            continue

        # Extract variables for current beam
        beam_data: dict[str, list] = {}
        for k, v in layers:
            try:
                if v.startswith("rh") and gedi_product == "L2A":
                    idx = int(v[2:])
                    vals = [round(h_bin[idx] * 100) for h_bin in gedi[f"{beam}/rh"][()]]
                elif v.startswith(("rh", "rch")) and gedi_product == "L2B" and product_version == "V003":
                    m = re.search(r'(\d+)$', v)
                    idx = int(m.group(1)) if m else None
                    vals = [h_bin[idx] for h_bin in gedi[f"{beam}/rch"][()]]
                elif v == "shot_number":
                    vals = [f"{_id:0>18}" for _id in shot_raw]
                else:
                    vals = list(gedi[f"{beam}/{v}"][()])

                if len(vals) != n:
                    raise ValueError(f"Length mismatch for '{v}': got {len(vals)}, expected {n}")

            except Exception as msg:  # noqa: BLE001
                anc.log(
                    handler=log_handler,
                    mode="exception",
                    file=f"{gedi_fp.name} ({beam})",
                    msg=f"Error extracting variable '{v}': {msg!s}"
                )
                anc.error_tracker.increment()
                vals = [pd.NA] * n  # keep column lengths aligned

            beam_data[k] = vals
        
        # Combine data for current beam with output data, ensuring that column lengths are aligned even in case of errors
        for k, vals in beam_data.items():
            out.setdefault(k, []).extend(vals)
        out.setdefault("acq_time", []).extend([str(acq_time)] * n)
    return out


def _filter_quality(
    df: DataFrame,
    log_handler: Logger,
    gedi_path: Path
) -> DataFrame:
    """
    Filters a given pandas.Dataframe containing GEDI data using the following 
    conditions:
    - quality_flag == 1
    - degrade_flag == 0
    - num_detectedmodes > 0
    - abs(elev - elev_dem_tdx) < 100
    
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
    cond = "quality_flag == 1 & degrade_flag == 0 & num_detectedmodes > 0 & " \
           "abs(elev - elev_dem_tdx) < 100"
    df = df.query(cond)
    df = df.drop(columns=['quality_flag', 'degrade_flag'])
    len_after = len_before - len(df)
    filt_perc = round((len_after / len_before) * 100, 2)
    msg = f"{str(len_after).zfill(5)}/{str(len_before).zfill(5)} " \
          f"({filt_perc}%) shots were filtered out based on default quality criteria."
    anc.log(handler=log_handler, mode='info', file=gedi_path.name, msg=msg)
    return df
