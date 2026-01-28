import logging
import re
import time
from stat import S_ISDIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def get_timestamp():
    """ Timestamp form YYYYMMDDHHMM: e.g. Christmas 2025 12:30 => 202512251230 """
    return time.strftime("%Y%m%d%H%M")


def remove_start(line):
    """ Remove INFO or other log start from a command to avoid having it doubled """
    info_split = re.compile(r'(INFO|WARNING|DEBUG|ERROR)\s*-\s*(.*)')
    match = info_split.search(line)
    if match:
        return match.group(2)
    return line


def _download_results(sftp, results_dir_path_remote, results_dir_path_local):
    """ Download from results_dir_path_remote to results_dir_path_local while skipping input folders """
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
