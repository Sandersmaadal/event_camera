#pragma once

#include <string>

#include <librealsense2/rs.hpp>
#include <opencv2/core.hpp>

#include <esod/Settings.h>


namespace esod {
class RealsenseCamera {
public:
    // Live camera; record_file empty = don't record.
    void open(const Settings &settings, const std::string &record_file = "");
    void open_file(const std::string &db3_file);   // replay
    void stop();
    // Newest color frame, or an empty Mat if none arrived since the last call.
    cv::Mat latest_color();
    bool finished();
private:
    rs2::pipeline pipe_;
    bool from_file_ = false;
};
}