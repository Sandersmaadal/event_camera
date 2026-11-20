// Background activity filter for one camera's events, used from Python as
// evdepth._evmatch.background_activity_filter (see evdepth/noise.py).
//
// An event is kept when one of its 8 neighbouring pixels had an event at most
// dt_us before it. A real edge moving over the sensor makes neighbouring pixels
// fire close together in time; noise events and hot pixels fire alone. Every
// event, kept or not, updates the time of its own pixel.
//
// Events come in sorted by time, at raw (not rectified) pixel positions.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <cstdint>
#include <limits>
#include <vector>

namespace py = pybind11;

py::array_t<bool> background_activity_filter(py::array_t<int64_t, py::array::c_style | py::array::forcecast> x,
                                             py::array_t<int64_t, py::array::c_style | py::array::forcecast> y,
                                             py::array_t<int64_t, py::array::c_style | py::array::forcecast> t,
                                             int width, int height, int64_t dt_us) {
    const int64_t n = t.size();
    auto xs = x.unchecked<1>(), ys = y.unchecked<1>(), ts = t.unchecked<1>();
    py::array_t<bool> keep(n);
    auto out = keep.mutable_unchecked<1>();

    const int64_t never = std::numeric_limits<int64_t>::min() / 2;
    std::vector<int64_t> last(static_cast<size_t>(width) * height, never);   // latest event per pixel

    {
        py::gil_scoped_release release;
        for (int64_t i = 0; i < n; ++i) {
            const int64_t px = xs(i), py_ = ys(i), ti = ts(i);
            bool supported = false;
            for (int64_t dy = -1; dy <= 1 && !supported; ++dy) {
                for (int64_t dx = -1; dx <= 1; ++dx) {
                    if (dx == 0 && dy == 0) continue;
                    const int64_t nx = px + dx, ny = py_ + dy;
                    if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
                    if (ti - last[ny * width + nx] <= dt_us) {
                        supported = true;
                        break;
                    }
                }
            }
            out(i) = supported;
            last[py_ * width + px] = ti;
        }
    }
    return keep;
}

void add_noise_filter(py::module_& m) {
    m.def("background_activity_filter", &background_activity_filter,
          "True for every event with a neighbouring event at most dt_us before it",
          py::arg("x"), py::arg("y"), py::arg("t"), py::arg("width"), py::arg("height"), py::arg("dt_us"));
}
