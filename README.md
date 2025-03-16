# Seedrcc sync

Connect to seedr.cc and download all of the files and folders into a directory of your choosing.

## Setup
1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
    1. `curl -LsSf https://astral.sh/uv/install.sh | sh`
1. `uv sync`

### Ease of use
Update your terminal profile to create an alias to this script:

`alias seedr_sync='uv run --project /full/path/to/project/ /full/path/to/project/seedr_sync.py'`
