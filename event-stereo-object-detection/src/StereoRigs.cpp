#include "esod/StereoRig.h"
#include <metavision/sdk/stream/camera.h>
#include <stdexcept>
#include <string>
#include <metavision/hal/facilities/i_camera_synchronization.h>

namespace esod
{
    namespace 
    {
    
    // Puts one camera in master or slave mode.
    void set_sync_mode(Metavision::Camera &camera, bool master, const std::string &name) {
        auto *sync = camera.get_device().get_facility<Metavision::I_CameraSynchronization>();
        if (!sync) {
            throw std::runtime_error("The " + name + " camera has no synchronization support");
        }
        const bool ok = master ? sync->set_mode_master() : sync->set_mode_slave();
        if (!ok) {
            throw std::runtime_error("Could not set the sync mode of the " + name + " camera");
        }
    }

    bool is_slave(Metavision::Camera &camera) {
        auto *sync = camera.get_device().get_facility<Metavision::I_CameraSynchronization>();
        return sync && sync->get_mode() == Metavision::I_CameraSynchronization::SyncMode::SLAVE;
    }
}

    void StereoRig::open(const esod::Settings &settings) {
        left_  = Metavision::Camera::from_serial(settings.left.serial);
        right_ = Metavision::Camera::from_serial(settings.right.serial);
        if (settings.left.role == "slave" && settings.right.role == "master")
        {
            set_sync_mode(left_, false, "left");
            set_sync_mode(right_, true, "right");
        } else if (settings.left.role == "master" && settings.right.role == "slave")
        {
            set_sync_mode(left_, true, "left");
            set_sync_mode(right_, false, "right");
        } else {
            throw std::runtime_error("settings.json needs exactly one \"master\" and one \"slave\" role");
        }
    }


    Metavision::Camera &StereoRig::left() {
        return left_;
    }

    Metavision::Camera &StereoRig::right() {
        return right_;
    }

    void StereoRig::start() {
    // The slave must start first: it waits for the master's clock.
        if (is_slave(left_)) {
            left_.start();
            right_.start();
        } else {
            right_.start();
            left_.start();
        }
}
    void StereoRig::stop() {
        left_.stop();
        right_.stop();
    }

    bool StereoRig::is_running() {
        return left_.is_running() && right_.is_running();
    }
}