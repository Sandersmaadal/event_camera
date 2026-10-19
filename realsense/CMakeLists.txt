cmake_minimum_required(VERSION 3.5)
project(realsense_viewer CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(realsense2 REQUIRED)
find_package(OpenCV REQUIRED COMPONENTS core highgui)

add_executable(view_rgb view_rgb.cpp)
target_include_directories(view_rgb PRIVATE ${OpenCV_INCLUDE_DIRS})
target_link_libraries(view_rgb PRIVATE realsense2::realsense2 ${OpenCV_LIBS})
target_compile_definitions(view_rgb PRIVATE RS_DATA_DIR="${CMAKE_SOURCE_DIR}/data")
