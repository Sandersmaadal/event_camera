#!/bin/bash
# Builds the C++ event matching into evdepth/_evmatch*.so.
# Needs a C++17 compiler, cmake and pybind11 (pip install pybind11).
# Run it again after every change to cpp/event_match.cpp.
set -e
cd "$(dirname "$0")"
PYTHON=${PYTHON:-python3}
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
      -DPython_EXECUTABLE="$(command -v "$PYTHON")" \
      -Dpybind11_DIR="$("$PYTHON" -m pybind11 --cmakedir)"
cmake --build build -j
echo "Built: $(ls ../evdepth/_evmatch*.so)"
