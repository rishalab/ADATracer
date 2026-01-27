#!/bin/bash
set -euo pipefail
echo "[ENTRYPOINT] Initializing Ada environment..."
cd /opt/ada_env
eval "$(alr printenv)"
LAL_BUILD_ROOT="/root/.local/share/alire/builds"
LAL_PYTHON_DIR=$(find "${LAL_BUILD_ROOT}" \
  -type d \
  -path "*libadalang*/python" \
  | head -n 1)
LAL_LIB_DIR=$(find "${LAL_BUILD_ROOT}" \
  -type f \
  -name "libadalang.so" \
  | head -n 1 \
  | xargs dirname)


if [[ -z "${LAL_PYTHON_DIR}" ]]; then
  echo "[ERROR] libadalang Python bindings not found"
  exit 1
fi
if [[ -z "${LAL_LIB_DIR}" ]]; then
  echo "[ERROR] libadalang shared library not found"
  exit 1
fi

export PYTHONPATH="${LAL_PYTHON_DIR}:${PYTHONPATH:-}"
export LD_LIBRARY_PATH="${LAL_LIB_DIR}:${LD_LIBRARY_PATH:-}"
echo "[ENTRYPOINT] PYTHONPATH=${PYTHONPATH}"
echo "[ENTRYPOINT] LD_LIBRARY_PATH=${LD_LIBRARY_PATH}"
cd /app
exec "$@"

