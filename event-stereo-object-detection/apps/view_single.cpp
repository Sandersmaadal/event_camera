// view_single: open one event camera (or a recording) and display its events.
//
//   ./view_single                 first camera found
//   ./view_single left            the left camera from settings.json (or: right)
//   ./view_single <serial>        the camera with this serial number
//   ./view_single recording.raw   play back a recorded file
//
// Press Q or Escape to quit.

#include <cstdint>
#include <exception>
#include <filesystem>
#include <iostream>
#include <string>
#include <metavision/hal/facilities/i_camera_synchronization.h>

#include <esod/Settings.h>

#include <metavision/sdk/base/events/event_cd.h>
#include <metavision/sdk/core/algorithms/periodic_frame_generation_algorithm.h>
#include <metavision/sdk/stream/camera.h> // SDK 4.x: metavision/sdk/driver/camera.h
#include <metavision/sdk/ui/utils/event_loop.h>
#include <metavision/sdk/ui/utils/window.h>

// Opens a live camera or a file. Both give back the same Camera type,
// so the rest of the program does not care which one it is.
Metavision::Camera open_camera(int argc, char *argv[], const esod::Settings &settings) {
    if (argc < 2) {
        return Metavision::Camera::from_first_available();
    }
    const std::string arg = argv[1];
    if (arg == "left") {
        return Metavision::Camera::from_serial(settings.left.serial);
    }
    if (arg == "right") {
        return Metavision::Camera::from_serial(settings.right.serial);
    }
    if (std::filesystem::exists(arg)) {
        return Metavision::Camera::from_file(arg);
    }
    return Metavision::Camera::from_serial(arg);
}


int main(int argc, char *argv[]) {
    Metavision::Camera cam;
    esod::Settings settings;

    try {
        settings = esod::load_settings();
        cam = open_camera(argc, argv, settings);
    } catch (const std::exception &e) {
        std::cerr << "Startup failed: " << e.what() << std::endl;
        return 1;
    }

    int camera_width  = cam.geometry().get_width();
    int camera_height = cam.geometry().get_height();

    // start the accumulation of events determined by accumulation_time_us
    auto frame_gen = Metavision::PeriodicFrameGenerationAlgorithm(camera_width, camera_height,
        settings.display.accumulation_time_us, settings.display.fps);

    cam.cd().add_callback([&](const Metavision::EventCD *begin, const Metavision::EventCD *end) {
        frame_gen.process_events(begin, end);
    });
    

    Metavision::Window window("Single_view Get Started", camera_width, camera_height,
                              Metavision::BaseWindow::RenderMode::BGR);
    
    window.set_keyboard_callback(
        [&window](Metavision::UIKeyEvent key, int scancode, Metavision::UIAction action, int mods) {
            if (action == Metavision::UIAction::RELEASE &&
                (key == Metavision::UIKeyEvent::KEY_ESCAPE || key == Metavision::UIKeyEvent::KEY_Q)) {
                window.set_close_flag();
            }
        });

    frame_gen.set_output_callback([&](Metavision::timestamp, cv::Mat &frame) { window.show(frame); });

    cam.start();
    std::cout << "Opened " << cam.get_camera_configuration().serial_number << "\n";
    auto *sync = cam.get_device().get_facility<Metavision::I_CameraSynchronization>();
    std::cout << (sync ? "sync available" : "sync NOT available") << std::endl;


    while (cam.is_running() && !window.should_close()) {
        // we poll events (keyboard, mouse etc.) from the system with a 20ms sleep to avoid using 100% of a CPU's core
        // and we push them into the window where the callback on the escape key will ask the windows to close
        static constexpr std::int64_t kSleepPeriodMs = 20;
        Metavision::EventLoop::poll_and_dispatch(kSleepPeriodMs);
    }
    cam.stop();
    return 0;
}