#include "esod/Recording.h"

#include <ctime>

namespace esod
{
std::filesystem::path new_recording_prefix(const std::filesystem::path &data_dir, std::string name) {
    std::filesystem::create_directories(data_dir);
    if (name.empty()) {
        const std::time_t now = std::time(nullptr);
        char stamp[32];
        std::strftime(stamp, sizeof(stamp), "%Y%m%d_%H%M%S", std::localtime(&now));
        name = stamp;
    }
    return data_dir / name;
}
} // namespace esod
