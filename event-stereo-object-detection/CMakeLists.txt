cmake_minimum_required(VERSION 3.5)
project(event_stereo CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(MetavisionSDK COMPONENTS core stream ui REQUIRED)
find_package(OpenCV REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(realsense2 REQUIRED)

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

add_library(esod_recording src/Recording.cpp)
target_include_directories(esod_recording PUBLIC include)

add_library(esod_realsense src/RealsenseCamera.cpp)
target_include_directories(esod_realsense PUBLIC include ${OpenCV_INCLUDE_DIRS})
target_link_libraries(esod_realsense PUBLIC esod_settings realsense2::realsense2 ${OpenCV_LIBS})


add_executable(view_realsense apps/view_realsense.cpp)
target_link_libraries(view_realsense PRIVATE
  esod_realsense
  esod_settings
  esod_recording
  realsense2::realsense2
  ${OpenCV_LIBS})



# One executable per file in apps/. Add new app names to this list.
foreach(app view_single view_dual)
  add_executable(${app} apps/${app}.cpp)
  target_link_libraries(${app} PRIVATE
    esod_settings
    esod_recording
    esod_framegen
    esod_stereo
    MetavisionSDK::ui
    ${OpenCV_LIBS})
endforeach()

add_executable(record_all apps/record_all.cpp)
target_link_libraries(record_all PRIVATE
  esod_settings
  esod_recording
  esod_framegen
  esod_stereo
  esod_realsense
  MetavisionSDK::ui
  nlohmann_json::nlohmann_json
  ${OpenCV_LIBS})