import datetime as _real_datetime
import importlib.util
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import genlayer_stub  # noqa: E402

sys.modules["genlayer"] = genlayer_stub


class Clock:
    now_ts = 1_800_000_000

    @classmethod
    def advance(cls, seconds):
        cls.now_ts += int(seconds)


class _FakeDatetimeClass:
    @staticmethod
    def now(tz=None):
        return _real_datetime.datetime.fromtimestamp(Clock.now_ts, tz=_real_datetime.timezone.utc)


class _FakeDatetimeModule:
    datetime = _FakeDatetimeClass


def load_contract(filename):
    path = ROOT / "contracts" / filename
    module = types.ModuleType("contract_under_test")
    module.__dict__["__file__"] = str(path)
    exec(compile(path.read_text(), str(path), "exec"), module.__dict__)
    module.datetime = _FakeDatetimeModule
    return module
