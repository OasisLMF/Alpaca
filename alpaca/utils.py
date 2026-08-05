import logging
import re
import time
from stat import S_ISDIR

logger = logging.getLogger(__name__)


def get_timestamp():
    """Generates a timestamp string.

    Returns:
        str: Timestamp in YYYYMMDDHHMM format (e.g., '202512251230' for
            December 25, 2025 at 12:30).
    """
    return time.strftime("%Y%m%d%H%M")


def remove_start(line):
    """Strip log level prefixes from SSH output to prevent duplicate formatting.
    Example: remove_start("INFO - Model run complete") => "Model run complete
             remove_start("No prefix here") => "No prefix here"
    Args:
        line: A line of text that may contain a log level prefix.

    Returns:
        str: The message portion without the log prefix, or the original
            line if no prefix pattern was found.
    """
    info_split = re.compile(r'(INFO|WARNING|DEBUG|ERROR)\s*-\s*(.*)')
    match = info_split.search(line)
    if match:
        return match.group(2)
    return line


def _download_results(sftp, results_dir_path_remote, results_dir_path_local):
    """Recursively download results via SFTP.

    Filtering rules:
        - Skipped entirely: 'fifo', 'static', 'work' directories
        - 'input' directory: Only downloads 'keys.csv' and 'keys-errors.csv'
        - All other files and directories: Downloaded recursively

    Args:
        sftp: An open paramiko SFTP client connection.
        results_dir_path_remote: pathlib.Path to the remote directory to download.
        results_dir_path_local: pathlib.Path to the local destination directory.

    Note:
        Creates the local directory structure as needed. Directories are
        traversed depth-first via recursive calls.
    """
    results_dir_path_local.mkdir(parents=True, exist_ok=True)
    skip_names = {"fifo", "static", "work"}
    input_files = {'keys.csv', 'keys-errors.csv'}
    for entry in sftp.listdir_attr(str(results_dir_path_remote)):
        # Get rid of fluff
        if entry.filename == "input":
            input_remote = results_dir_path_remote / "input"
            input_local = results_dir_path_local / "input"
            input_local.mkdir(parents=True, exist_ok=True)
            for input_entry in sftp.listdir_attr(str(input_remote)):
                if input_entry.filename in input_files:
                    remote_file = input_remote / input_entry.filename
                    local_file = input_local / input_entry.filename
                    sftp.get(str(remote_file), str(local_file))
            continue
        if entry.filename in skip_names:
            logger.info(f"Skipping download of folder: {entry.filename}")
            continue
        # Important ones
        remote_file = results_dir_path_remote / entry.filename
        local_file = results_dir_path_local / entry.filename
        if S_ISDIR(entry.st_mode):
            _download_results(sftp, remote_file, local_file)
        else:
            sftp.get(str(remote_file), str(local_file))
