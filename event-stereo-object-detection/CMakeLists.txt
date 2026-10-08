cmake_minimum_required(VERSION 3.5)
project(event_stereo CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(MetavisionSDK COMPONENTS core stream ui REQUIRED)
find_package(OpenCV REQUIRED COMPONENTS core imgproc)
find_package(nlohmann_json REQUIRED)

add_library(esod_settings src/Settings.cpp)
target_include_directories(esod_settings PUBLIC include)
target_link_libraries(esod_settings PRIVATE nlohmann_json::nlohmann_json)
target_compile_definitions(esod_settings PRIVATE
  EVS_SETTINGS_PATH="${CMAKE_SOURCE_DIR}/settings.json")

add_library(esod_framegen src/Framegenerator.cpp)
target_include_directories(esod_framegen PUBLIC include ${OpenCV_INCLUDE_DIRS})
target_link_libraries(esod_framegen PUBLIC
  MetavisionSDK::core
  MetavisionSDK::stream
  ${OpenCV_LIBS})

add_library(esod_stereo src/StereoRigs.cpp)
target_include_directories(esod_stereo PUBLIC include)
target_link_libraries(esod_stereo PUBLIC MetavisionSDK::core MetavisionSDK::stream)



# One executable per file in apps/. Add new app names to this list.
foreach(app view_single view_dual)
  add_executable(${app} apps/${app}.cpp)
  target_link_libraries(${app} PRIVATE
    esod_settings
    esod_framegen
    esod_stereo
    MetavisionSDK::ui
    ${OpenCV_LIBS})
endforeach()