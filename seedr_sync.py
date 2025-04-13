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
import asyncio
from pathlib import Path
import os
from dataclasses import dataclass

import aiohttp
from tqdm import tqdm
from dotenv import load_dotenv
from docopt import docopt
from aioseedrcc import (
    Login,
    Seedr
)

@dataclass
class File:
    """Class to track and interact with a seedr file"""
    api: Seedr
    name: str
    path: Path
    id: int

    def __repr__(self) -> str:
        return (f"{self.__class__.__name__}(api={self.api.__class__.__name__}, name={self.name}, "
                +f"path={self.path}, id={self.id})")

    def __str__(self) -> str:
        return self.__repr__()

    async def delete(self) -> None:
        """
        Delete the file in seedr
        """
        print(f"Deleting seedr file: {self.name}")
        await self.api.delete_item(self.id, 'file')

    async def download(self, location: Path) -> None:
        """
        Download the file to a location

        Args:
            location [Path]: System path to download the file to
        """
        details = await self.file_details()
        url = details['url']

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
                    with open(location, "wb") as f:
                        with tqdm(total=total_size, unit='B', unit_scale=True, desc=str(location), leave=True) as pbar:
                            while True:
                                chunk = await resp.content.read(1024)
                                if not chunk:
                                    break
                                f.write(chunk)
                                # Update the progress bar by the size of the chunk
                                pbar.update(len(chunk))
                else:
                    print(f"Failed to download {url}: Status {resp.status}")
                    self._download_was_successful = False
                    return
        self._download_was_successful = True

    async def file_details(self) -> dict:
        """
        Request file details such as download link from seedr
        """
        if hasattr(self, '_file_details'):
            return self._file_details
        return await self.api.fetch_file(self.id)

    def get_was_download_successful(self) -> bool:
        """
        Return whether or not the download was successful

        Return: bool if known. None if unknown (file download wasn't attempted)
        """
        if not hasattr(self, '_download_was_successful'):
            return None
        return self._download_was_successful


async def get_all_files(seedr: Seedr, folder_id: str | int ="root", current_path: Path = None) -> list[File]:
    """
    Recursively get all files from

    Args:
        seedr: Seedr API sdk
        folder_id [int | str]: Folder ID to request contents of
        current_path [Path | None]: Current seedr path for the folder

    Returns list[File]
    """
    if not current_path:
        current_path = Path()
    files = []
    folder = await seedr.list_contents(folder_id=folder_id)
    for item in folder['files']:
        file_path = current_path.joinpath(item["name"])
        files.append(File(seedr,
                          name=item['name'],
                          path=file_path,
                          id=int(item["folder_file_id"])))

    for subfolder in folder['folders']:
        subfolder_path = current_path.joinpath(subfolder['name'])
        subfiles = await get_all_files(seedr, subfolder['id'], subfolder_path)
        files.extend(subfiles)
    return files

async def process_file(file_info: File):
    """
    Process a single file
    """
    if path := args['--output']:
        local_path = Path(path) / file_info.path
    else:
        local_path = Path('.') / file_info.path

    local_path.parent.mkdir(parents=True, exist_ok=True)
    await file_info.download(local_path)

async def delete_successful_file(file_info: File) -> None:
    """
    Delete the file only if it was successfully downloaded

    Arg:
        file_info [File]
    """
    if file_info.get_was_download_successful():
        await file_info.delete()

async def is_folder_empty(seedr: Seedr, folder_id: int| str) -> bool:
    """
    Check whether a folder is empty
    """
    r = await seedr.list_contents(folder_id)
    return len(r['files']) == 0 and len(r['folders']) == 0

async def delete_empty_folders(seedr: Seedr) -> None:
    """
    Delete empty folders in Seedr
    """
    folders = await seedr.list_contents('root')
    for folder in folders['folders']:
        if not await is_folder_empty(seedr, folder['id']):
            continue
        print(f"Deleting folder: {folder['name']}")
        await seedr.delete_item(folder['id'], 'folder')


async def main():
    async with Login(os.environ.get('SEEDRCC_EMAIL'), os.environ.get('SEEDRCC_PASSWORD')) as login:
        await login.authorize()
        async with Seedr(token=login.token, token_refresh_callback=login.authorize) as seedr:
            print("Retrieving file list from Seedr.cc...")
            files = await get_all_files(seedr)
            tasks = [process_file(file_info) for file_info in files]
            print(f"Starting download and processing of {len(tasks)} files...")
            await asyncio.gather(*tasks)
            print("Deleting successfully downloaded files...")
            tasks = [delete_successful_file(file_info) for file_info in files]
            await asyncio.gather(*tasks)
            await delete_empty_folders(seedr)

if __name__ == "__main__":
    args = docopt(__doc__)
    load_dotenv(override=False)
    asyncio.run(main())