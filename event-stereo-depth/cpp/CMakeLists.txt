# Builds evdepth/_evmatch (the C++ event matching and noise filter) as a Python module.
# Use cpp/build.sh rather than calling cmake yourself.
cmake_minimum_required(VERSION 3.15)
project(evmatch CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()

find_package(pybind11 CONFIG REQUIRED)
pybind11_add_module(_evmatch event_match.cpp noise_filter.cpp)
target_compile_options(_evmatch PRIVATE -Wall -Wextra)

# Put the module next to the Python code, so that "from evdepth import _evmatch" finds it.
set_target_properties(_evmatch PROPERTIES LIBRARY_OUTPUT_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/../evdepth)
