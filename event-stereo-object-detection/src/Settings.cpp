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

StreamSettings read_stream(const nlohmann::json &json, const std::string &key, const int fps) {
    const nlohmann::json &block = json.at(key);
    StreamSettings stream;
    stream.width = block.at("width");
    stream.height = block.at("height");
    stream.fps = fps;
    return stream;
}

RealsenseSettings read_realsense(const nlohmann::json &json, const std::string &key) {
    const nlohmann::json &block = json.at(key);
    RealsenseSettings rs;
    int fps = block.at("fps");
    rs.rgb = read_stream(block, "rgb", fps);
    rs.depth = read_stream(block, "depth", fps);
    return rs;
}


RecordingSettings read_recording(const nlohmann::json &json, const std::string &key) {
    const nlohmann::json &block = json.at(key);
    RecordingSettings rec;
    std::filesystem::path dir = block.at("data_dir").get<std::string>();
    if (dir.is_relative()) {
        dir = std::filesystem::path(EVS_SETTINGS_PATH).parent_path() / dir;
    }
    rec.data_dir = dir;
    return rec;
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
    settings.realsense = read_realsense(json, "realsense");
    settings.recording = read_recording(json, "recording");
    return settings;
}
} // namespace esod 