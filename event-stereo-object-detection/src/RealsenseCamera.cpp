#include "esod/RealsenseCamera.h"

namespace esod
{
void RealsenseCamera::open(const Settings &settings, const std::string &record_file) {
    const StreamSettings  &rgb = settings.realsense.rgb;
    const StreamSettings & depth = settings.realsense.depth;

    rs2::config cfg;
    // start camera stream
    cfg.enable_stream(RS2_STREAM_COLOR, rgb.width, rgb.height, RS2_FORMAT_BGR8, rgb.fps);
    // start distance estimation stream
    cfg.enable_stream(RS2_STREAM_DEPTH, depth.width, depth.height, RS2_FORMAT_Z16, depth.fps);

    if (!record_file.empty()) {
        cfg.enable_record_to_file(record_file);
    }
    pipe_.start(cfg);
}

void RealsenseCamera::open_file(const std::string &db3_file) {
    rs2::config cfg;
    cfg.enable_device_from_file(db3_file, false);
    pipe_.start(cfg);
    from_file_ = true;
}

void RealsenseCamera::stop() {
    pipe_.stop();
}

cv::Mat RealsenseCamera::latest_color() {
    rs2::frameset fs;
    if (!pipe_.poll_for_frames(&fs)) {
        return cv::Mat();
    }
    rs2::video_frame color = fs.get_color_frame();
    if (!color) {
        return cv::Mat();
    }
    const cv::Mat wrapped(cv::Size(color.get_width(), color.get_height()), CV_8UC3,
        const_cast<void*>(color.get_data()), cv::Mat::AUTO_STEP);
    return wrapped.clone();
}

bool RealsenseCamera::finished() {
    if (!from_file_) return false;
    rs2::playback playback = pipe_.get_active_profile().get_device().as<rs2::playback>();
    return playback.current_status() == RS2_PLAYBACK_STATUS_STOPPED;
}
}