# nidozo — LLM vs LLM Pokémon battle arena
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__: str = _pkg_version("nidozo")
except PackageNotFoundError:
    __version__ = "unknown"
