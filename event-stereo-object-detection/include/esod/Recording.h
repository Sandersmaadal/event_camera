#pragma once

#include <filesystem>
#include <string>

namespace esod {
// Path prefix for a new recording inside data_dir, e.g. <data_dir>/test01.
// With no name, the current date and time is used, e.g. <data_dir>/20261009_143012.
// data_dir is created if it does not exist.
std::filesystem::path new_recording_prefix(const std::filesystem::path &data_dir, std::string name);
}
