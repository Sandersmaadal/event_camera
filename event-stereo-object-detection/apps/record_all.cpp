// record_all: record both event cameras and the RealSense at the same time.
// ./record_all                     # saved as <data_dir>/<date_time>_*
// ./record_all test01              # saved as <data_dir>/test01_*
// ./record_all --no-window test01  # no display, e.g. when started over SSH
// <data_dir> is "recording.data_dir" in settings.json.
//
// Files written:
//   <prefix>_left.raw, <prefix>_right.raw   event cameras (synchronized)
//   <prefix>_realsense.db3                 RealSense color + depth
//   <prefix>_info.json                     start/stop time and clock reference
//
// The event cameras count time in microseconds from their own start. To place
// events on the system clock: system_time_us = t + (anchor.system_time_us - anchor.event_time_us).
// RealSense timestamps are already on the system clock (milliseconds).
//
// Press Q or Escape, or close the window, to stop. With --no-window: Ctrl+C.

#include <atomic>
#include <chrono>
#include <csignal>
#include <ctime>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <mutex>
#include <string>
#include <thread>

#include <nlohmann/json.hpp>
#include <opencv2/imgproc.hpp>

#include <esod/Framegenerator.h>
#include <esod/RealsenseCamera.h>
#include <esod/Recording.h>
#include <esod/Settings.h>
#include <esod/StereoRig.h>

#include <metavision/sdk/base/events/event_cd.h>
#include <metavision/sdk/stream/camera.h>
#include <metavision/sdk/ui/utils/event_loop.h>
#include <metavision/sdk/ui/utils/window.h>


namespace
{
std::atomic<bool> stop_requested{false};

void on_sigint(int) {
    stop_requested = true;
}

std::int64_t system_time_us() {
    return std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}

std::string utc_string(std::int64_t time_us) {
    const std::time_t seconds = time_us / 1000000;
    char text[32];
    std::strftime(text, sizeof(text), "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&seconds));
    return text;
}

// Links the event cameras' clock to the system clock: the system time at
// which the first batch of events arrived, and the timestamp of its first event.
struct ClockAnchor {
    std::mutex mutex;
    bool set = false;
    std::int64_t system_time_us = 0;
    std::int64_t event_time_us = 0;
};

void write_info(const std::filesystem::path &file, const esod::Settings &settings,
                std::int64_t start_us, std::int64_t stop_us, ClockAnchor &anchor) {
    nlohmann::json info;
    info["start_utc"] = utc_string(start_us);
    info["start_system_time_us"] = start_us;
    if (stop_us != 0) {
        info["stop_utc"] = utc_string(stop_us);
        info["stop_system_time_us"] = stop_us;
    }
    {
        std::lock_guard<std::mutex> lock(anchor.mutex);
        if (anchor.set) {
            info["event_clock_anchor"] = {
                {"system_time_us", anchor.system_time_us},
                {"event_time_us", anchor.event_time_us},
            };
        }
    }
    info["left_camera"] = {{"serial", settings.left.serial}, {"role", settings.left.role}};
    info["right_camera"] = {{"serial", settings.right.serial}, {"role", settings.right.role}};
    info["realsense"] = {
        {"rgb", {{"width", settings.realsense.rgb.width}, {"height", settings.realsense.rgb.height}}},
        {"depth", {{"width", settings.realsense.depth.width}, {"height", settings.realsense.depth.height}}},
        {"fps", settings.realsense.rgb.fps},
    };
    std::ofstream(file) << info.dump(4) << std::endl;
}
}


int main(int argc, char *argv[])
{
    bool show_window = true;
    std::string name;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--no-window") {
            show_window = false;
        } else if (name.empty() && arg[0] != '-') {
            name = arg;
        } else {
            std::cerr << "Usage: record_all [--no-window] [name]" << std::endl;
            return 1;
        }
    }

    esod::Settings settings;
    esod::StereoRig rig;
    esod::RealsenseCamera realsense;
    std::filesystem::path prefix;
    try {
        settings = esod::load_settings();
        prefix = esod::new_recording_prefix(settings.recording.data_dir, name);
        rig.open(settings);
        realsense.open(settings, prefix.string() + "_realsense.db3");
        rig.start_recording(prefix);
    } catch (const std::exception &e) {
        std::cerr << "Startup failed: " << e.what() << std::endl;
        return 1;
    }

    Metavision::Camera &left = rig.left();
    Metavision::Camera &right = rig.right();
    const int width  = left.geometry().get_width();
    const int height = left.geometry().get_height();
    if (right.geometry().get_width() != width || right.geometry().get_height() != height) {
        std::cerr << "The two cameras have different resolutions." << std::endl;
        return 1;
    }

    ClockAnchor anchor;
    left.cd().add_callback([&anchor](const Metavision::EventCD *begin, const Metavision::EventCD *end) {
        if (begin == end) return;
        std::lock_guard<std::mutex> lock(anchor.mutex);
        if (!anchor.set) {
            anchor.system_time_us = system_time_us();
            anchor.event_time_us = begin->t;
            anchor.set = true;
        }
    });

    esod::Framegenerator left_frames(left, settings.display.accumulation_time_us, settings.display.fps);
    esod::Framegenerator right_frames(right, settings.display.accumulation_time_us, settings.display.fps);

    // The RealSense image is scaled to the event cameras' height.
    const esod::StreamSettings &rgb = settings.realsense.rgb;
    const cv::Size rgb_size(rgb.width * height / rgb.height, height);
    cv::Mat rgb_frame(rgb_size, CV_8UC3, cv::Scalar(0, 0, 0));

    const std::filesystem::path info_file = prefix.string() + "_info.json";
    const std::int64_t start_us = system_time_us();
    std::signal(SIGINT, on_sigint);

    rig.start();
    std::cout << "Recording to " << prefix.string() << "_*" << std::endl;
    if (!show_window) {
        std::cout << "Press Ctrl+C to stop." << std::endl;
    }

    // _info.json is written as soon as the clock anchor is known, so it
    // exists even if the recording ends without a clean stop.
    bool info_written = false;
    auto write_info_when_anchored = [&] {
        if (info_written) return;
        {
            std::lock_guard<std::mutex> lock(anchor.mutex);
            if (!anchor.set) return;
        }
        write_info(info_file, settings, start_us, 0, anchor);
        info_written = true;
    };

    if (show_window) {
        Metavision::Window window("record_all", 2 * width + rgb_size.width, height,
                                  Metavision::BaseWindow::RenderMode::BGR);
        window.set_keyboard_callback(
            [&window](Metavision::UIKeyEvent key, int scancode, Metavision::UIAction action, int mods) {
                if (action == Metavision::UIAction::RELEASE &&
                    (key == Metavision::UIKeyEvent::KEY_ESCAPE || key == Metavision::UIKeyEvent::KEY_Q)) {
                    window.set_close_flag();
                }
            });

        const cv::Scalar white(255, 255, 255);
        cv::Mat combined;
        while (rig.is_running() && !window.should_close() && !stop_requested) {
            const cv::Mat new_rgb = realsense.latest_color();
            if (!new_rgb.empty()) {
                cv::resize(new_rgb, rgb_frame, rgb_size);
            }
            cv::hconcat(std::vector<cv::Mat>{left_frames.latest_frame(), right_frames.latest_frame(), rgb_frame},
                        combined); // left | right | realsense

            cv::putText(combined, "left", cv::Point(10, 25), cv::FONT_HERSHEY_SIMPLEX, 0.7, white, 2);
            cv::putText(combined, "right", cv::Point(width + 10, 25), cv::FONT_HERSHEY_SIMPLEX, 0.7, white, 2);
            cv::putText(combined, "realsense", cv::Point(2 * width + 10, 25), cv::FONT_HERSHEY_SIMPLEX, 0.7, white, 2);

            window.show(combined);
            Metavision::EventLoop::poll_and_dispatch(20); // sleeps up to 20 ms
            write_info_when_anchored();
        }
    } else {
        while (rig.is_running() && !stop_requested) {
            // The RealSense is recorded by librealsense itself; reading frames
            // here only keeps its frame queue from filling up.
            realsense.latest_color();
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
            write_info_when_anchored();
        }
    }

    // Stop the cameras before the frame generators are destroyed.
    rig.stop_recording();
    rig.stop();
    realsense.stop();
    write_info(info_file, settings, start_us, system_time_us(), anchor);
    std::cout << "Saved " << prefix.string() << "_left.raw, _right.raw, _realsense.db3, _info.json" << std::endl;
    return 0;
}
