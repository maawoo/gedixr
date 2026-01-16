from pathlib import Path
from typing import Optional, List
import typer
from typing_extensions import Annotated

from gedixr.extract import extract_data
from gedixr.download import download_data

app = typer.Typer(
    name="gedixr",
    help="GEDI L2A/L2B data extraction and processing tools",
    add_completion=False,
)


@app.command()
def extract(
    directory: Annotated[
        Path,
        typer.Argument(
            help="Root directory to recursively search for GEDI L2A/L2B files",
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
        ),
    ],
    product: Annotated[
        str,
        typer.Option(
            "--product", "-p",
            help="GEDI product type: 'L2A' or 'L2B'",
        ),
    ] = "L2B",
    beams: Annotated[
        Optional[str],
        typer.Option(
            "--beams", "-b",
            help="Which beams to extract: 'power' (power beams), 'coverage' (coverage beams), or comma-separated beam names (e.g., 'BEAM0101,BEAM0110'). Default: all beams",
        ),
    ] = None,
    filter_month_min: Annotated[
        int,
        typer.Option(
            "--filter-month-min",
            help="Minimum month to filter shots (1-12)",
            min=1,
            max=12,
        ),
    ] = 1,
    filter_month_max: Annotated[
        int,
        typer.Option(
            "--filter-month-max",
            help="Maximum month to filter shots (1-12)",
            min=1,
            max=12,
        ),
    ] = 12,
    subset_vector: Annotated[
        Optional[List[Path]],
        typer.Option(
            "--subset-vector", "-v",
            help="Path(s) to vector file(s) for spatial subsetting (can be used multiple times). Default: no spatial subsetting",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    quality_filter: Annotated[
        bool,
        typer.Option(
            "--quality-filter/--no-quality-filter",
            help="Apply quality filtering to GEDI data",
        ),
    ] = True,
):
    """
    Extract data from GEDI L2A or L2B files.
    
    The extracted data will be saved as GeoParquet files in the 'extracted' 
    subdirectory of the input directory.
    """
    # Process beams parameter
    beams_list = None
    if beams is not None and beams not in ['power', 'coverage']:
        beams_list = [b.strip() for b in beams.split(',')]
    elif beams in ['power', 'coverage']:
        beams_list = beams
    
    # Process filter_month
    filter_month = (filter_month_min, filter_month_max)
    
    # Process subset_vector
    subset_vector_list = None
    if subset_vector is not None:
        subset_vector_list = subset_vector if len(subset_vector) > 1 else subset_vector[0]
    
    typer.echo(f"Extracting GEDI {product} data from: {directory}")
    typer.echo(f"Quality filter: {quality_filter}")
    typer.echo(f"Month filter: {filter_month_min} - {filter_month_max}")
    
    try:
        result, out_path = extract_data(
            directory=directory,
            gedi_product=product,
            beams=beams_list,
            filter_month=filter_month,
            subset_vector=subset_vector_list,
            apply_quality_filter=quality_filter,
        )
        
        typer.secho("✓ Extraction completed successfully!", fg=typer.colors.GREEN)
        
        if isinstance(result, dict):
            typer.echo(f"Processed {len(result)} spatial subsets")
            for k, v in result.items():
                if v['path'] is not None:
                    typer.echo(f"  - {k}: {v['path']}")
        else:
            typer.echo(f"Processed {len(result)} total shots")
            if out_path is not None:
                typer.echo(f"Output saved to: {out_path}")
            
    except Exception as e:
        typer.secho(f"✗ Error during extraction: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command()
def download(
    directory: Annotated[
        Path,
        typer.Argument(
            help="Directory where downloaded files will be saved",
            file_okay=False,
            dir_okay=True,
        ),
    ],
    product: Annotated[
        str,
        typer.Option(
            "--product", "-p",
            help="GEDI product type: 'L2A' or 'L2B'",
        ),
    ],
    time_start: Annotated[
        Optional[str],
        typer.Option(
            "--time-start", "-s",
            help="Start date in YYYY-MM-DD format",
        ),
    ] = None,
    time_end: Annotated[
        Optional[str],
        typer.Option(
            "--time-end", "-e",
            help="End date in YYYY-MM-DD format",
        ),
    ] = None,
    subset_vector: Annotated[
        Optional[Path],
        typer.Option(
            "--subset-vector", "-v",
            help="Path to vector file for spatial subsetting",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    bbox: Annotated[
        Optional[str],
        typer.Option(
            "--bbox",
            help="Bounding box as 'min_lon,min_lat,max_lon,max_lat'",
        ),
    ] = None,
    job_id: Annotated[
        Optional[str],
        typer.Option(
            "--job-id",
            help="Harmony job ID to resume a previous download",
        ),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet", "-q",
            help="Suppress progress messages",
        ),
    ] = False,
):
    """
    Download GEDI data using NASA Harmony API.
    
    Requires either --subset-vector or --bbox for spatial subsetting.
    If --job-id is provided, other parameters (time-range, subset-*) are ignored.
    """
    # Validate directory
    if not directory.exists():
        typer.secho(f"✗ Directory does not exist: {directory}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    # Process time range
    time_range = None
    if time_start and time_end:
        time_range = (time_start, time_end)
    elif time_start or time_end:
        typer.secho("✗ Either both --time-start and --time-end must be provided, or neither", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    # Process bbox
    subset_bbox = None
    if bbox:
        try:
            bbox_parts = [float(x.strip()) for x in bbox.split(',')]
            if len(bbox_parts) != 4:
                raise ValueError
            subset_bbox = tuple(bbox_parts)
        except ValueError:
            typer.secho("✗ Invalid bbox format. Use: 'min_lon,min_lat,max_lon,max_lat'", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    # Validate spatial subset
    if job_id is None and subset_vector is None and subset_bbox is None:
        typer.secho("✗ Either --subset-vector or --bbox must be provided", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    if not quiet:
        typer.echo(f"Downloading GEDI {product} data to: {directory}")
    
    try:
        file_paths, returned_job_id = download_data(
            directory=directory,
            gedi_product=product,
            time_range=time_range,
            subset_vector=subset_vector,
            subset_bbox=subset_bbox,
            job_id=job_id,
            verbose=not quiet,
        )
        
        typer.secho("✓ Download completed successfully!", fg=typer.colors.GREEN)
        
    except KeyboardInterrupt:
        typer.secho("\n✗ Download interrupted by user", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=130)
    except Exception as e:
        typer.secho(f"✗ Error during download: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command()
def version():
    """Show the version of gedixr."""
    from importlib.metadata import version as get_version
    try:
        ver = get_version("gedixr")
        typer.echo(f"gedixr version: {ver}")
    except Exception:
        typer.echo("gedixr version: unknown (package not installed)")


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
