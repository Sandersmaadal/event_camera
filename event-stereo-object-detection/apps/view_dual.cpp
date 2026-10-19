// view_dual: show the left and right event cameras side by side in one window.
// The cameras are synchronized.
// ./view_dual                           # live, nothing saved
// ./view_dual --record                  # live and saved as <data_dir>/<date_time>_left/right.raw
// ./view_dual --record test01           # live and saved as <data_dir>/test01_left/right.raw
// ./view_dual a_left.raw a_right.raw    # replay a saved pair
// <data_dir> is "recording.data_dir" in settings.json.
//
// Press Q or Escape to quit.

#include <exception>
#include <filesystem>
#include <iostream>
#include <string>

#include <opencv2/imgproc.hpp>
 
#include <esod/Framegenerator.h>
#include <esod/Recording.h>
#include <esod/Settings.h>
#include <esod/StereoRig.h>

#include <metavision/sdk/stream/camera.h>
#include <metavision/sdk/ui/utils/event_loop.h>
#include <metavision/sdk/ui/utils/window.h>


int main(int argc, char *argv[])
{
    const bool record = (argc == 2 || argc == 3) && std::string(argv[1]) == "--record";
    const bool replay = argc == 3 && !record;
    if (argc != 1 && !record && !replay) {
        std::cerr << "Usage: view_dual [--record [name] | left.raw right.raw]" << std::endl;
        return 1;
    }

    esod::Settings settings;
    esod::StereoRig rig;
    try {
        settings = esod::load_settings();
        if (replay) {
            rig.open_files(argv[1], argv[2]);
        } else {
            rig.open(settings);
        }
        if (record) {
            const std::filesystem::path prefix =
                esod::new_recording_prefix(settings.recording.data_dir, argc == 3 ? argv[2] : "");
            rig.start_recording(prefix);
            std::cout << "Recording to " << prefix.string() << "_left.raw / _right.raw" << std::endl;
        }
    } catch (const std::exception &e) {
        std::cerr << "Startup failed: " << e.what() << std::endl;
        return 1;
    }

    Metavision::Camera &left = rig.left();
    Metavision::Camera &right = rig.right();

    int width  = left.geometry().get_width();
    int height = left.geometry().get_height();
    if (right.geometry().get_width() != width || right.geometry().get_height() != height) {
        std::cerr << "The two cameras have different resolutions." << std::endl;
        return 1;
    }

    esod::Framegenerator left_frames(left, settings.display.accumulation_time_us, settings.display.fps);
    esod::Framegenerator right_frames(right, settings.display.accumulation_time_us, settings.display.fps);

    Metavision::Window window("view_dual", 2 * width, height, Metavision::BaseWindow::RenderMode::BGR);

    window.set_keyboard_callback(
        [&window](Metavision::UIKeyEvent key, int scancode, Metavision::UIAction action, int mods) {
            if (action == Metavision::UIAction::RELEASE &&
                (key == Metavision::UIKeyEvent::KEY_ESCAPE || key == Metavision::UIKeyEvent::KEY_Q)) {
                window.set_close_flag();
            }
        });

    rig.start();
 
    // Main thread: about 50 times per second, fetch the newest frame from
    // each camera, join them and show the result.
    const cv::Scalar white(255, 255, 255);
    cv::Mat combined;
    while (left.is_running() && right.is_running() && !window.should_close()) {
        const cv::Mat left_frame  = left_frames.latest_frame();
        const cv::Mat right_frame = right_frames.latest_frame();

        cv::hconcat(left_frame, right_frame, combined); // left | right

        cv::putText(combined, "left", cv::Point(10, 25), cv::FONT_HERSHEY_SIMPLEX, 0.7, white, 2);
        cv::putText(combined, "right", cv::Point(width + 10, 25), cv::FONT_HERSHEY_SIMPLEX, 0.7, white, 2);

        window.show(combined);
        Metavision::EventLoop::poll_and_dispatch(20); // sleeps up to 20 ms
    }
 
    // Stop the cameras before the frame generators are destroyed.
    if (record) {
        rig.stop_recording();
    }
    rig.stop();
    return 0;
}