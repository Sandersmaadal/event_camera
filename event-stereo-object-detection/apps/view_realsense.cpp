// view_realsense: show the RealSense color stream.
// ./view_realsense                      # live, nothing saved
// ./view_realsense --record             # live and saved as <data_dir>/<date_time>_realsense.db3
// ./view_realsense --record test01      # live and saved as <data_dir>/test01_realsense.db3
// ./view_realsense a_realsense.db3      # replay a saved recording
// <data_dir> is "recording.data_dir" in settings.json.
// The .db3 file holds both the color and the depth stream, with timestamps.
//
// Press Q or Escape, or close the window, to quit.


#include <exception>
#include <filesystem>
#include <iostream>
#include <string>

#include <opencv2/opencv.hpp>

#include <esod/Recording.h>
#include <esod/Settings.h>
#include <esod/RealsenseCamera.h>


int main(int argc, char *argv[])
{
    const bool record = (argc == 2 || argc == 3) && std::string(argv[1]) == "--record";
    const bool replay = argc == 2 && !record;
    if (argc != 1 && !record && !replay) {
        std::cerr << "Usage: view_realsense [--record [name] | file.db3]" << std::endl;
        return 1;
    }

    esod::RealsenseCamera camera;
    try {
        if (replay) {
            camera.open_file(argv[1]);
        } else{
            const esod::Settings settings = esod::load_settings();
            std::string record_file;
            if (record) {
                const std::filesystem::path prefix =
                    esod::new_recording_prefix(settings.recording.data_dir, argc == 3 ? argv[2] : "");
                record_file = prefix.string() + "_realsense.db3";
            }
            camera.open(settings, record_file);
            if (record) {
                std::cout << "Recording to " << record_file << std::endl;
            }
        }
    } catch (const std::exception &e) {
        std::cerr << "Startup failed: " << e.what() << std::endl;
        return 1;
    }

    const std::string window = "Realsense RGB stream";
    cv::namedWindow(window);
    while (!camera.finished())
    {
        const cv::Mat img = camera.latest_color();
        if (!img.empty()) {
            cv::imshow(window, img);
        }
        int key = cv::waitKey(10);
        if (key == 'q' || key == 27 || cv::getWindowProperty(window, cv::WND_PROP_VISIBLE) < 1) break;
    }

    // Stopping the pipeline also closes the .db3 file properly.
    camera.stop();
    return 0;
}
