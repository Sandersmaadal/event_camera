#include "esod/Settings.h"

#include<fstream>
#include<stdexcept>
#include<nlohmann/json.hpp>
#include<cstdint>


namespace esod
{
namespace
{
CameraSettings read_camera(const nlohmann::json &json, const std::string &key) {
    const nlohmann::json &block = json.at(key);
    CameraSettings camera;
    camera.serial = block.at("serial").get<std::string>();
    camera.role   = block.at("role").get<std::string>();
    return camera;
}

DisplaySettings read_display(const nlohmann::json &json, const std::string &key) {
    const nlohmann::json &block = json.at(key);
    DisplaySettings disp;
    disp.accumulation_time_us = block.at("accumulation_time_us");
    disp.fps = block.at("fps");
    return disp;
}
}

Settings load_settings() {
    // EVS_SETTINGS_PATH is set in CMakeLists.txt.
    std::ifstream file(EVS_SETTINGS_PATH);
    if (!file) {
        throw std::runtime_error(std::string("Cannot open ") + EVS_SETTINGS_PATH);
    }
    const nlohmann::json json = nlohmann::json::parse(file);
 
    Settings settings;
    settings.left  = read_camera(json, "left_camera");
    settings.right = read_camera(json, "right_camera");
    settings.display = read_display(json, "display");
    return settings;
}
} // namespace esod 