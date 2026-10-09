#pragma once

#include <filesystem>

#include <metavision/sdk/stream/camera.h>
#include <esod/Settings.h>

namespace esod
{
class StereoRig
{
    public:
        StereoRig() = default;
        // Opens the live cameras from settings.json and sets up master/slave sync.
        void open(const esod::Settings &settings);
        // Opens a recorded pair for replay instead of live cameras.
        void open_files(const std::filesystem::path &left_file, const std::filesystem::path &right_file);

        // Saves both streams to <prefix>_left.raw and <prefix>_right.raw.
        void start_recording(const std::filesystem::path &prefix);
        void stop_recording();


        Metavision::Camera &left();
        Metavision::Camera &right();

        void start();
        void stop();
        bool is_running();

    private:
        Metavision::Camera left_;
        Metavision::Camera right_;
};
}