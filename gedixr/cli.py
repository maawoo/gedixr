from pathlib import Path
from typing import Optional, List
import typer
from typing_extensions import Annotated

from gedixr import gedi

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
            help="Which beams to extract: 'full' (power beams), 'coverage' (coverage beams), or comma-separated beam names (e.g., 'BEAM0101,BEAM0110'). Default: all beams",
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
    temp_unpack_zip: Annotated[
        bool,
        typer.Option(
            "--temp-unpack-zip/--no-temp-unpack-zip",
            help="Unpack zip archives in temporary directories",
        ),
    ] = False,
):
    """
    Extract data from GEDI L2A or L2B files.
    
    The extracted data will be saved as GeoParquet files in the 'extracted' 
    subdirectory of the input directory.
    """
    # Process beams parameter
    beams_list = None
    if beams is not None and beams not in ['full', 'coverage']:
        beams_list = [b.strip() for b in beams.split(',')]
    elif beams in ['full', 'coverage']:
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
        result = gedi.extract_data(
            directory=directory,
            gedi_product=product,
            temp_unpack_zip=temp_unpack_zip,
            beams=beams_list,
            filter_month=filter_month,
            subset_vector=subset_vector_list,
            apply_quality_filter=quality_filter,
        )
        
        typer.secho("✓ Extraction completed successfully!", fg=typer.colors.GREEN)
        
        if isinstance(result, dict):
            typer.echo(f"Processed {len(result)} spatial subsets")
        else:
            typer.echo(f"Processed {len(result)} total shots")
            
    except Exception as e:
        typer.secho(f"✗ Error during extraction: {e}", fg=typer.colors.RED, err=True)
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
