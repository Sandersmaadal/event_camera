#pragma  once

#include<string>
#include <cstdint>
#include <filesystem>

namespace esod{
struct CameraSettings{
    std::string serial;
    std::string role;
};

struct DisplaySettings {
    std::int32_t accumulation_time_us;
    double fps;
};

struct StreamSettings {
    int width;
    int height;
    int fps;
};

struct RealsenseSettings {
    StreamSettings rgb;
    StreamSettings depth;
};

struct RecordingSettings {
    // Where recordings are saved. A relative path in settings.json is
    // relative to the project folder.
    std::filesystem::path data_dir;
};

struct Settings {
    CameraSettings left;
    CameraSettings right;
    DisplaySettings display;
    RealsenseSettings realsense;
    RecordingSettings recording;
};

Settings load_settings();
}