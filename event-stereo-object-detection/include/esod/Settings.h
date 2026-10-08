#pragma  once

#include<string>

namespace esod{
struct CameraSettings{
    std::string serial;
    std::string role;
};

struct DisplaySettings {
    std::int32_t accumulation_time_us;
    double fps;
};

struct Settings {
    CameraSettings left;
    CameraSettings right;
    DisplaySettings display;
};



Settings load_settings();
}