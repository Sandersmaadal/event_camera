// Live view of the RealSense RGB stream, optionally recorded with depth.
// ./view_rgb                         # live view
// ./view_rgb --record                # live and saved as data/<date_time>_realsense.db3
// ./view_rgb --record test01         # live and saved as data/test01_realsense.db3
// ./view_rgb data/test01_realsense.db3   # replay a recording
// Press 'q' or ESC (or Ctrl+C in the terminal) to quit.
//
// A recording contains colour and depth. Frame timestamps are in ms on the
// computer's clock (global time domain), so they can be matched against the
// event recordings. <prefix>_realsense.txt stores the clock reference.

#include <librealsense2/rs.hpp>
#include <opencv2/core.hpp>
#include <opencv2/highgui.hpp>

#include <chrono>
#include <csignal>
#include <cstdlib>
#include <ctime>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>

namespace {

// Set by Ctrl+C, so the loop ends and the recording file is closed properly.
volatile std::sig_atomic_t stop_requested = 0;
void on_signal(int) { stop_requested = 1; }

constexpr int kWidth = 640;
constexpr int kHeight = 480;
constexpr int kFps = 30;

// Path prefix for a new recording, e.g. <project>/data/test01.
// With no name, the current date and time is used, e.g. <project>/data/20261009_143012.
std::filesystem::path new_recording_prefix(std::string name) {
  if (name.empty()) {
    const std::time_t now = std::time(nullptr);
    char stamp[32];
    std::strftime(stamp, sizeof(stamp), "%Y%m%d_%H%M%S", std::localtime(&now));
    name = stamp;
  }
  const std::filesystem::path dir = RS_DATA_DIR;
  std::filesystem::create_directories(dir);
  return dir / name;
}

// Microseconds since the Unix epoch on the computer's clock.
long long host_time_us() {
  using namespace std::chrono;
  return duration_cast<microseconds>(system_clock::now().time_since_epoch()).count();
}

}  // namespace

int main(int argc, char** argv) try {
  const bool record = (argc == 2 || argc == 3) && std::string(argv[1]) == "--record";
  const bool replay = argc == 2 && !record;
  if (argc > 3 || (argc == 3 && !record)) {
    std::cerr << "Usage: view_rgb [--record [name] | recording.db3]" << std::endl;
    return EXIT_FAILURE;
  }

  rs2::config cfg;
  std::filesystem::path prefix;
  if (replay) {
    cfg.enable_device_from_file(argv[1], false);  // false: play once, don't loop
  } else {
    cfg.enable_stream(RS2_STREAM_COLOR, kWidth, kHeight, RS2_FORMAT_BGR8, kFps);
    if (record) {
      cfg.enable_stream(RS2_STREAM_DEPTH, kWidth, kHeight, RS2_FORMAT_Z16, kFps);
      prefix = new_recording_prefix(argc == 3 ? argv[2] : "");
      cfg.enable_record_to_file(prefix.string() + "_realsense.db3");
    }
  }

  rs2::pipeline pipe;
  rs2::pipeline_profile profile = pipe.start(cfg);

  auto dev = profile.get_device();
  if (replay) {
    std::cout << "Replaying " << argv[1] << std::endl;
  } else {
    std::cout << "Streaming from " << dev.get_info(RS2_CAMERA_INFO_NAME)
              << " (serial " << dev.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER) << ") at "
              << kWidth << "x" << kHeight << " @ " << kFps << " fps" << std::endl;
  }
  if (record) std::cout << "Recording to " << prefix.string() << "_realsense.db3" << std::endl;

  const char* window = "RealSense RGB";
  cv::namedWindow(window, cv::WINDOW_AUTOSIZE);

  // Installed after librealsense and the window are set up, which may set their own.
  std::signal(SIGINT, on_signal);
  std::signal(SIGTERM, on_signal);

  bool clock_reference_written = false;
  while (!stop_requested) {
    rs2::frameset frames;
    if (replay) {
      // A finished file stops delivering frames instead of throwing.
      if (!pipe.try_wait_for_frames(&frames, 1000)) break;
    } else {
      frames = pipe.wait_for_frames();
    }
    rs2::video_frame color = frames.get_color_frame();
    if (!color) continue;

    // Written once, from the first colour frame: lets the recorded timestamps be
    // checked against the host clock and against the event recordings.
    if (record && !clock_reference_written) {
      std::ofstream ref(prefix.string() + "_realsense.txt");
      ref << std::fixed << std::setprecision(3)
          << "host_time_us " << host_time_us() << '\n'
          << "first_color_timestamp_ms " << color.get_timestamp() << '\n'
          << "timestamp_domain "
          << rs2_timestamp_domain_to_string(color.get_frame_timestamp_domain()) << '\n'
          << "serial " << dev.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER) << '\n'
          << "resolution " << kWidth << "x" << kHeight << " @ " << kFps << " fps\n";
      clock_reference_written = true;
    }

    // Wraps the RealSense buffer without copying; valid until `color` is released.
    cv::Mat image(cv::Size(color.get_width(), color.get_height()), CV_8UC3,
                  const_cast<void*>(color.get_data()), cv::Mat::AUTO_STEP);
    cv::imshow(window, image);

    int key = cv::waitKey(1);
    if (key == 'q' || key == 27) break;
    if (cv::getWindowProperty(window, cv::WND_PROP_VISIBLE) < 1) break;
  }

  pipe.stop();  // Also closes the recording file.
  return EXIT_SUCCESS;
} catch (const rs2::error& e) {
  std::cerr << "RealSense error calling " << e.get_failed_function() << "("
            << e.get_failed_args() << "): " << e.what() << '\n';
  return EXIT_FAILURE;
} catch (const std::exception& e) {
  std::cerr << e.what() << '\n';
  return EXIT_FAILURE;
}
