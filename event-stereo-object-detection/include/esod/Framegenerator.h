# pragma once
#include <cstdint>
#include <mutex>

#include <opencv2/core.hpp>

#include <metavision/sdk/core/algorithms/periodic_frame_generation_algorithm.h>
#include <metavision/sdk/stream/camera.h>

namespace esod {
class Framegenerator
{
    public:
        Framegenerator(Metavision::Camera &cam, std::int32_t accumulation_time_us,
            float fps);
        cv::Mat latest_frame();

    private:
        std::mutex mutex_;
        Metavision::PeriodicFrameGenerationAlgorithm frame_gen_;
        cv::Mat latest_;

};
}