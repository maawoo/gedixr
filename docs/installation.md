# Installation

## Latest Version from GitHub

### 1. Create and activate an environment

Create a conda environment with the required dependencies:

```bash
conda env create --file https://raw.githubusercontent.com/maawoo/gedixr/main/environment.yml
conda activate gedixr_env
```

!!! tip
    We recommend using [Mamba](https://mamba.readthedocs.io/en/latest/index.html) as a faster alternative to Conda.

### 2. Install gedixr

Install the package into the activated environment:

```bash
pip install git+https://github.com/maawoo/gedixr.git
```

## Specific Version

See the [Tags](https://github.com/maawoo/gedixr/tags) section of the repository for available versions:

```bash
conda env create --file https://raw.githubusercontent.com/maawoo/gedixr/v0.5.0/environment.yml
conda activate gedixr_env
pip install git+https://github.com/maawoo/gedixr.git@v0.5.0
```
