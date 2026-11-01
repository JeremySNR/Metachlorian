from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from metachlorian.config import Settings
from metachlorian.llm import LimitReached, _Ledger


def reserve(directory):
    try:
        _Ledger(Settings(data_dir=Path(directory))).take(20)
        return True
    except LimitReached:
        return False


def test_request_cap_is_shared_across_processes(tmp_path):
    with ProcessPoolExecutor(max_workers=4) as pool:
        accepted = sum(pool.map(reserve, [str(tmp_path)] * 32))
    assert accepted == _Ledger(Settings(data_dir=tmp_path)).used() == 20
