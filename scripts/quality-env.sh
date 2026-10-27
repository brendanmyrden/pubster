# Source from a launcher that has set ROOT to the absolute project root.
export TMPDIR="$ROOT/.quality/tmp"
export PIP_CACHE_DIR="$ROOT/.quality/cache/pip"
export XDG_CACHE_HOME="$ROOT/.quality/cache"
export XDG_CONFIG_HOME="$ROOT/.quality/config"
export XDG_DATA_HOME="$ROOT/.quality/data"
export PYTHONPYCACHEPREFIX="$ROOT/.quality/cache/pycache"
export MPLCONFIGDIR="$ROOT/.quality/cache/matplotlib"
export NUMBA_CACHE_DIR="$ROOT/.quality/cache/numba"
export GX_ANALYTICS_ENABLED=false
export GE_USAGE_STATS=false
export POLARS_MAX_THREADS=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export PYTHONNOUSERSITE=1
