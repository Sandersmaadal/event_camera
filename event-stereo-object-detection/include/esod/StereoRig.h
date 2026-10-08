#pragma once
 
#include <metavision/sdk/stream/camera.h>
#include <esod/Settings.h>

namespace esod
{
class StereoRig
{
    public:
        StereoRig() = default;
        void open(const esod::Settings &settings);


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