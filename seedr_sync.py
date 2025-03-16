"""
Script that connects to seedr.cc and pulls down each of the files.

Usage:
    seedr_sync.py [-o PATH] [-v]
    seedr_sync.py (-h | --help)

Options:
    -o PATH, --output PATH  Path to download to (defaults to working directory)
    -v, --verbose           Enable verbose output.
    -h, --help              Show this help message and exit.

Description:
    This script connects to Seedr.cc and performs file downloads. If an output location
    is provided via --ouput, the files/folders will be downloaed there. If it's not
    provided, the working directory is used.
    
    The below environment variables are used for seedr.cc connection. A .env file can be used
    to load them in, or they can be set before the script is ran:
        SEEDR_CC_EMAIL
        SEEDR_CC_PASSWORD
"""
from dotenv import load_dotenv
import asyncio
import os
from pathlib import Path

from docopt import docopt
import aiohttp
from seedrapi.api import SeedrAPI
from tqdm import tqdm


# Asynchronous function to download a file from a URL
# Returns -1 if failure, 0 if successful
async def download_file(url, path) -> int:
    # Create timeout for 5 hours due to possible slow connections and large files
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(3600*5)) as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                total_size = resp.headers.get('Content-Length')
                if total_size is not None:
                    total_size = int(total_size)
                else:
                    total_size = None
                
                # Open the file for writing
                with open(path, "wb") as f:
                    # Create a tqdm progress bar
                    with tqdm(total=total_size, unit='B', unit_scale=True, desc=path, leave=True) as pbar:
                        while True:
                            chunk = await resp.content.read(1024)
                            if not chunk:
                                break
                            f.write(chunk)
                            # Update the progress bar by the size of the chunk
                            pbar.update(len(chunk))
            else:
                print(f"Failed to download {url}: Status {resp.status}")
                return -1
    return 0

# delete a file
async def delete_file(seedr, file_id):
    loop = asyncio.get_event_loop()
    # Currently a bug with the delete API https://github.com/AnjanaMadu/SeedrAPI/issues/9
    await loop.run_in_executor(None, seedr.delete_file, file_id)


# Process a single file: download and unzip if necessary
async def process_file(seedr, file_info):
    loop = asyncio.get_event_loop()
    # Get file details synchronously in a thread
    file_details = await loop.run_in_executor(None, seedr.get_file, file_info["id"])
    download_link = file_details["url"]  # Assumes API returns a dict with "url"
    if args['--output']:
        local_path = Path(args['--output']) / file_info["path"]
    else:
        local_path = Path('.') / file_info["path"]

    local_path.parent.mkdir(parents=True, exist_ok=True)
    result = await download_file(download_link, str(local_path))
    if result == -1:
        return
    await delete_file(seedr, file_info["id"])

# Recursively get all files from Seedr.cc
async def get_all_files(seedr, folder_id="root", current_path=""):
    loop = asyncio.get_event_loop()
    # Get folder contents synchronously in a thread
    folder = await loop.run_in_executor(None, seedr.get_folder, folder_id)
    files = []
    # Process files in the current folder
    for item in folder["files"]:
        file_path = os.path.join(current_path, item["name"])
        files.append({"path": file_path, "id": item["folder_file_id"], "name": item["name"]})

    for subfolder in folder["folders"]:
        subfolder_path = os.path.join(current_path, subfolder["name"])
        subfiles = await get_all_files(seedr, subfolder["id"], subfolder_path)
        files.extend(subfiles)
    return files

# Main async function
async def main():

    seedr = SeedrAPI(os.environ.get('SEEDRCC_EMAIL'),
                     os.environ.get('SEEDRCC_PASSWORD'))

    print("Retrieving file list from Seedr.cc...")
    all_files = await get_all_files(seedr)

    tasks = [process_file(seedr, file_info) for file_info in all_files]
    print(f"Starting download and processing of {len(tasks)} files...")
    await asyncio.gather(*tasks)
    print("All files have been downloaded and processed.")

if __name__ == "__main__":
    args = docopt(__doc__)
    load_dotenv(override=False)
    asyncio.run(main())
