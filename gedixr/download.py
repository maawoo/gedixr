from pathlib import Path
import datetime as dt
import json
from typing import Optional
import warnings
import geopandas as gpd
import earthaccess
from harmony import BBox, Client, Collection, Request, CapabilitiesRequest

import gedixr.constants as con


def download_data(directory: str | Path,
                  gedi_product: str,
                  time_range: Optional[tuple[str, str]] = None,
                  subset_vector: Optional[str | Path] = None,
                  subset_bbox: Optional[tuple[float, float, float, float]] = None,
                  job_id: Optional[str] = None,
                  verbose: bool = True
                  ) -> list[Path]:
    """
    Download GEDI data using NASA Harmony API based on a time range and spatial subset.
    Please note that if `subset_vector` is provided, the download will be subset to the
    bounding box of the vector geometry and not the exact geometry itself. To perform
    precise spatial subsetting, use the vector file again during data extraction.
    
    Parameters
    ----------
    directory : str or Path
        Directory where downloaded files will be saved. A subdirectory named after the
        GEDI product will be created within this directory and files will be saved there.
    gedi_product : str
        GEDI product name: 'L2A' or 'L2B'
    time_range : tuple of str, optional
        Time range as (start_date, end_date) in format 'YYYY-MM-DD'
    subset_vector : str or Path, optional
        Path to vector file for spatial subsetting. Please note that the download will 
        be subset to the bounding box of the vector geometry and not the exact geometry 
        itself. To perform precise spatial subsetting, use the vector file again during 
        data extraction. If provided, takes precedence over subset_bbox.
    subset_bbox : tuple of float, optional
        Bounding box as (min_lon, min_lat, max_lon, max_lat).
    job_id : str, optional
        Harmony job ID to resume a previous download. If provided, a new request
        will not be submitted and other parameters (time_range, subset_*) are ignored.
    verbose : bool, default=True
        Whether to print progress messages
    
    Returns
    -------
    tuple of (list of Path, str)
        Downloaded file paths and the job ID for potential resumption.
    
    Examples
    --------
    >>> # Initial download
    >>> files, job_id = download_data(
    ...     directory='data/gedi',
    ...     gedi_product='L2A',
    ...     time_range=('2020-01-01', '2020-01-31'),
    ...     subset_bbox=(-10, 40, 5, 50)
    ... )
    >>> # Resume interrupted download
    >>> files, job_id = download_data(
    ...     directory='data/gedi',
    ...     gedi_product='L2A',
    ...     job_id=job_id
    ... )
    """
    short_name = con.PRODUCT_MAPPING.get(gedi_product.upper())
    if short_name is None:
        raise ValueError(f"Parameter 'gedi_product': expected to be one of "
                        f"{list(con.PRODUCT_MAPPING.keys())}; got '{gedi_product}' instead")

    directory = Path(directory)
    if not directory.exists():
        raise ValueError(f"Directory does not exist: {directory}")
    download_dir = directory.joinpath(gedi_product.upper())
    download_dir.mkdir(parents=True, exist_ok=True)

    harmony_client = _authenticate_earthdata()

    job_id_file = download_dir.joinpath('.harmony_job_id')
    if job_id is None:
        if job_id_file.exists():
            saved_job_id = job_id_file.read_text().strip()
            if verbose:
                print(f"Found existing job ID from previous run: {saved_job_id}")
                print("To resume this job, pass job_id parameter.")
                print("Submitting new request...")
        
        if time_range is not None:
            time_range = {'start': dt.datetime.fromisoformat(time_range[0]),
                          'stop': dt.datetime.fromisoformat(time_range[1])}
        
        bbox = _get_bbox(subset_vector, subset_bbox)

        capabilities = harmony_client.submit(CapabilitiesRequest(short_name=short_name))
        collection = Collection(id=capabilities['conceptId'])
        request = Request(
            collection=collection,
            spatial=bbox,
            temporal=time_range
        )
        if not request.is_valid():
            raise ValueError(f"Invalid Harmony request: {request.validate()}")
        
        job_id = harmony_client.submit(request)        
        job_id_file.write_text(job_id)
        if verbose:
            print(f"Job submitted with ID: {job_id}")
            print(f"Job ID saved to: {job_id_file}")
    else:
        if verbose:
            print(f"Resuming job with ID: {job_id}")
        
        job_id_file.write_text(job_id)

    if verbose:
        print("Files will be processed by Harmony before proceeding with download...")
    
    try:
        result_json = harmony_client.result_json(job_id, show_progress=verbose)
        status = result_json.get('status', 'unknown')
        if status == 'failed':
            _failed_status(download_dir, job_id, job_id_file, result_json)
        elif status not in ['successful', 'complete']:
            warnings.warn(
                f"Harmony job status is '{status}'. Proceeding with download but results may be incomplete.",
                UserWarning
            )
        if verbose:
            print("Processing complete. Starting download...")
        
        results = harmony_client.download_all(
            job_id,
            directory=str(download_dir),
            overwrite=True
        )    
        
        file_paths = [Path(f.result()) for f in results]
        if verbose:
            print(f"Downloaded {len(file_paths)} file(s) to {download_dir}")
        if len(file_paths) == 0:
            warnings.warn(
                "No files were downloaded. This may indicate an issue with the request or data availability.",
                UserWarning
            )
        
        if job_id_file.exists():
            job_id_file.unlink()
        
        return file_paths, job_id
    
    except (KeyboardInterrupt, Exception) as e:
        if verbose:
            if isinstance(e, KeyboardInterrupt):
                print(f"\nDownload interrupted by user. Job ID saved to: {job_id_file}")
            else:
                print(f"\nDownload interrupted due to error: {e}")
                print(f"Job ID saved to: {job_id_file}")
            print("To resume, run:")
            print(f"  download_data(directory='{directory}', gedi_product='{gedi_product}', job_id='{job_id}')")
            print("or use the CLI with --job-id option.")
        raise


def _authenticate_earthdata() -> Client:
    """ Authenticate with Earthdata and return a Harmony client. """
    auth = earthaccess.login(strategy='all', persist=True)
    harmony_client = Client(auth=(auth.username, auth.password)) 
    return harmony_client


def _get_bbox(subset_vector: Optional[str | Path], 
              subset_bbox: Optional[tuple[float, float, float, float]]) -> BBox:
    """
    Extract bounding box from vector file or bbox coordinates.
    
    Parameters
    ----------
    subset_vector : str or Path, optional
        Path to vector file (shapefile, GeoJSON, etc.)
    subset_bbox : tuple of float, optional
        Bounding box as (min_lon, min_lat, max_lon, max_lat)
    
    Returns
    -------
    BBox
        Harmony BBox object
    
    Raises
    ------
    ValueError
        If neither parameter is provided
    """
    if subset_vector is None and subset_bbox is None:
        raise ValueError("Either subset_vector or subset_bbox must be provided")
    
    if subset_vector is not None:
        if subset_bbox is not None:
            warnings.warn(
                "Both subset_vector and subset_bbox provided; using subset_vector",
                UserWarning
            )
        
        aoi = gpd.read_file(subset_vector)
        bounds = aoi.to_crs(4326).total_bounds
        return BBox(bounds[0], bounds[1], bounds[2], bounds[3])
    
    return BBox(*subset_bbox)


def _failed_status(download_dir : Path, 
                   job_id: str, 
                   job_id_file: Path,
                   result_json: dict) -> None:
        """Handle failed Harmony job status by saving error details and raising RuntimeError."""
        error_json_path = download_dir.joinpath(f'{job_id}_error.json')
        with open(error_json_path, 'w') as f:
            json.dump(result_json, f, indent=2)
        
        errors = result_json.get('errors', [])
        error_message = result_json.get('message', 'Unknown error')
        
        error_counts = {}
        for error in errors:
            msg = error.get('message', '')
            error_counts[msg] = error_counts.get(msg, 0) + 1
        
        err_msg = f"Harmony job failed: {error_message}\n"
        err_msg += f"Error details saved to: {error_json_path}\n"
        
        if error_counts:
            err_msg += f"\nTotal errors: {len(errors)}\n"
            err_msg += "Error summary:\n"
            for msg, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True):
                err_msg += f"  - {count}x: {msg}\n"
        
        if job_id_file.exists():
            job_id_file.unlink()
        
        raise RuntimeError(err_msg)
