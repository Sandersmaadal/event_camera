#include "esod/Framegenerator.h"
#include <metavision/sdk/base/events/event_cd.h>

namespace esod 
{
Framegenerator::Framegenerator(Metavision::Camera &cam, std::int32_t accumulation_time_us,
            float fps) : frame_gen_(cam.geometry().get_width(), cam.geometry().get_height(),
            accumulation_time_us, fps), latest_(cam.geometry().get_height(), cam.geometry().get_width(),
            CV_8UC3, cv::Scalar(0, 0, 0))
{
    frame_gen_.set_output_callback([this](Metavision::timestamp, cv::Mat &frame)
    {
        std::lock_guard<std::mutex> lock(mutex_); 
        frame.copyTo(latest_);
    });

    cam.cd().add_callback([this](const Metavision::EventCD *begin, const Metavision::EventCD *end){
        frame_gen_.process_events(begin, end);
    });
}

cv::Mat Framegenerator::latest_frame()
{
    std::lock_guard<std::mutex> lock(mutex_);
    return latest_.clone();
};
}