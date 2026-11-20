// Event-by-event stereo matching in C++, used from Python as evdepth._evmatch
// (see depth_events.py).
//
// Build:  cpp/build.sh   (again after every change to this file)
//
// There are no time windows. Left and right events are processed together in
// time order, and each camera keeps the time of its latest event per pixel and
// polarity. When a left event arrives it is matched right
// away, using only events up to its own time:
//
// 1. The recent left events in the patch around it (at most max_age old) are
//    compared with the right camera's latest events at every disparity: cost
//    min(time difference / max_dt, 1), averaged over the recent events. The
//    right camera's rows within time_rows above and below count too.
// 2. The lowest-cost disparity must be cheap enough (max_cost) and clearly
//    better than the disparities further than one pixel away (min_margin).
// 3. Left-right check (lr_tol >= 0): the right camera's patch at the matched
//    position is matched back to the left in the same way; both must agree.
// 4. Sub-pixel disparity: a parabola through the costs at best-1, best, best+1.
//    (Taking it from the sub-pixel event positions instead was tried and gave
//    the same accuracy on the lab tests; see the README.)
//
// The events are cut into time chunks that run in parallel. Each chunk first
// replays the max_age + max_dt of events before it, which is all the history
// a match can use, so the result is the same as when run in one go.
//
// Events come in as rectified whole-pixel positions (x, y), polarity on
// (1 = ON) and time t in microseconds, sorted by time. The right pixel that matches left pixel x at disparity d is
// x - sign * d.

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <thread>
#include <vector>

namespace py = pybind11;

using Ints = py::array_t<int64_t, py::array::c_style | py::array::forcecast>;
using Flags = py::array_t<uint8_t, py::array::c_style | py::array::forcecast>;

constexpr double INF = std::numeric_limits<double>::infinity();
constexpr int64_t NEVER = std::numeric_limits<int64_t>::min() / 2;   // "no event yet"

// What happened to a left event (returned as "status").
enum Status : int8_t { NO_SUPPORT = 0, HIGH_COST = 1, NOT_UNIQUE = 2, LEFT_RIGHT = 3, MATCHED = 4 };

// One camera's events in plain vectors.
struct Events {
    std::vector<int64_t> x, y, t;
    std::vector<uint8_t> on;

    Events(const Ints& x_, const Ints& y_, const Flags& on_, const Ints& t_) {
        const py::ssize_t n = x_.size();
        if (y_.size() != n || on_.size() != n || t_.size() != n)
            throw std::invalid_argument("x, y, on and t must have the same length");
        x.assign(x_.data(), x_.data() + n);
        y.assign(y_.data(), y_.data() + n);
        on.assign(on_.data(), on_.data() + n);
        t.assign(t_.data(), t_.data() + n);
    }
    size_t size() const { return x.size(); }
};

struct Settings {
    int W, H, min_disp, max_disp, sign, patch;
    double max_dt_us, max_age_us;
    int time_rows, min_events;
    double max_cost, min_margin, lr_tol;
    int D() const { return max_disp - min_disp; }
};

// Time of one camera's latest event per pixel and polarity.
struct Latest {
    int W, H;
    std::vector<int64_t> t;

    Latest(int W_, int H_) : W(W_), H(H_), t(2 * static_cast<size_t>(W_) * H_, NEVER) {}
    int64_t index(int on, int64_t y, int64_t x) const { return (static_cast<int64_t>(on) * H + y) * W + x; }
    void add(const Events& ev, size_t i) { t[index(ev.on[i], ev.y[i], ev.x[i])] = ev.t[i]; }
};

struct Recent { int64_t x, y, t; int on; };

// Recent events of one camera in the patch around (x, y), at most max_age old at time t.
void recent_in_patch(int64_t x, int64_t y, int64_t t, const Latest& own, const Settings& s,
                     std::vector<Recent>& recent) {
    recent.clear();
    const int r = s.patch / 2;
    for (int64_t py_ = std::max<int64_t>(0, y - r); py_ <= std::min<int64_t>(s.H - 1, y + r); ++py_)
        for (int64_t px = std::max<int64_t>(0, x - r); px <= std::min<int64_t>(s.W - 1, x + r); ++px)
            for (int on = 0; on < 2; ++on) {
                const int64_t k = own.index(on, py_, px);
                if (own.t[k] != NEVER && t - own.t[k] <= s.max_age_us)
                    recent.push_back({px, py_, own.t[k], on});
            }
}

// Mean time cost of the recent events at every disparity, against the other
// camera. The other camera's pixel for x at disparity d is x + direction * d.
void patch_costs(const std::vector<Recent>& recent, const Latest& other, int direction, const Settings& s,
                 std::vector<double>& cost, std::vector<double>& dt) {
    // Per recent event all disparities at once: along a row of the other
    // camera the pixels lie next to each other in memory, so the innermost
    // loop reads memory in order (fast).
    const int D = s.D();
    std::fill(cost.begin(), cost.end(), 0.0);
    for (const Recent& e : recent) {
        std::fill(dt.begin(), dt.end(), INF);       // per disparity: time to the closest event
        for (int dy = -s.time_rows; dy <= s.time_rows; ++dy) {
            const int64_t row = e.y + dy;
            if (row < 0 || row >= s.H) continue;
            const int64_t* other_row = &other.t[other.index(e.on, row, 0)];
            for (int k = 0; k < D; ++k) {
                const int64_t x_match = e.x + static_cast<int64_t>(direction) * (s.min_disp + k);
                if (x_match < 0 || x_match >= s.W || other_row[x_match] == NEVER) continue;
                dt[k] = std::min(dt[k], std::abs(static_cast<double>(e.t - other_row[x_match])));
            }
        }
        for (int k = 0; k < D; ++k) cost[k] += std::min(dt[k] / s.max_dt_us, 1.0);
    }
    for (int k = 0; k < D; ++k) cost[k] = recent.empty() ? 1.0 : cost[k] / recent.size();
}

// Parabola through the costs at best-1, best, best+1: offset in -0.5 .. 0.5.
double parabola_offset(const std::vector<double>& cost, int best) {
    if (best < 1 || best > static_cast<int>(cost.size()) - 2) return 0.0;
    const double c0 = cost[best - 1], c1 = cost[best], c2 = cost[best + 1];
    const double denom = c0 - 2 * c1 + c2;
    return std::abs(denom) > 1e-6 ? std::clamp(0.5 * (c0 - c2) / denom, -0.5, 0.5) : 0.0;
}

struct Result {
    std::vector<float> disparity, cost, margin;
    std::vector<int32_t> support;
    std::vector<int8_t> status;
    explicit Result(size_t n) : disparity(n, NAN), cost(n, NAN), margin(n, NAN), support(n, 0), status(n, NO_SUPPORT) {}
};

// Index of the lowest cost, and the margin to the best one further than one disparity away.
int best_disparity(const std::vector<double>& cost, double& margin) {
    const int best = static_cast<int>(std::min_element(cost.begin(), cost.end()) - cost.begin());
    double second = INF;
    for (int k = 0; k < static_cast<int>(cost.size()); ++k)
        if (std::abs(k - best) > 1) second = std::min(second, cost[k]);
    margin = second - cost[best];
    return best;
}

// Match left events i0 .. i1-1. Events from left index iw and right index jw
// on only build up the state (the history before the chunk).
void match_chunk(const Events& left, const Events& right, const Settings& s, size_t iw, size_t jw,
                 size_t i0, size_t i1, Result& out) {
    Latest last_left(s.W, s.H), last_right(s.W, s.H);
    std::vector<Recent> recent, recent_right;
    std::vector<double> cost(s.D()), cost_back(s.D()), dt(s.D());
    size_t j = jw;
    for (size_t i = iw; i < i1; ++i) {
        const int64_t t = left.t[i];
        for (; j < right.size() && right.t[j] <= t; ++j) last_right.add(right, j);   // right events up to now
        last_left.add(left, i);
        if (i < i0) continue;                                                       // history only

        recent_in_patch(left.x[i], left.y[i], t, last_left, s, recent);
        out.support[i] = static_cast<int32_t>(recent.size());
        if (static_cast<int>(recent.size()) < s.min_events) continue;
        patch_costs(recent, last_right, -s.sign, s, cost, dt);

        double margin;
        const int best = best_disparity(cost, margin);
        out.cost[i] = static_cast<float>(cost[best]);
        out.margin[i] = static_cast<float>(margin);
        if (cost[best] > s.max_cost) { out.status[i] = HIGH_COST; continue; }
        if (margin < s.min_margin) { out.status[i] = NOT_UNIQUE; continue; }

        if (s.lr_tol >= 0) {             // match the right patch at the found position back to the left
            const int64_t x_right = left.x[i] - static_cast<int64_t>(s.sign) * (s.min_disp + best);
            recent_in_patch(std::clamp<int64_t>(x_right, 0, s.W - 1), left.y[i], t, last_right, s, recent_right);
            patch_costs(recent_right, last_left, s.sign, s, cost_back, dt);
            double unused;
            if (recent_right.empty() || std::abs(best_disparity(cost_back, unused) - best) > s.lr_tol) {
                out.status[i] = LEFT_RIGHT;
                continue;
            }
        }

        out.disparity[i] = static_cast<float>(s.min_disp + best + parabola_offset(cost, best));
        out.status[i] = MATCHED;
    }
}

py::dict match_events(const Ints& xl, const Ints& yl, const Flags& onl, const Ints& tl,
                      const Ints& xr, const Ints& yr, const Flags& onr, const Ints& tr,
                      int W, int H, int min_disp, int max_disp, int sign, int patch,
                      double max_dt_us, double max_age_us, int time_rows, int min_events,
                      double max_cost, double min_margin, double lr_tol, int threads) {
    const Events left(xl, yl, onl, tl), right(xr, yr, onr, tr);
    const Settings s{W, H, min_disp, max_disp, sign, patch, max_dt_us, max_age_us, time_rows, min_events,
                     max_cost, min_margin, lr_tol};
    const size_t n = left.size();
    Result out(n);
    {
        py::gil_scoped_release no_gil;
        if (threads <= 0) threads = std::max(1u, std::thread::hardware_concurrency());
        const size_t chunks = std::max<size_t>(1, std::min<size_t>(threads, n / 5000));
        const int64_t history_us = static_cast<int64_t>(max_age_us + max_dt_us) + 1;
        std::vector<std::thread> workers;
        for (size_t c = 0; c < chunks; ++c) {
            const size_t i0 = n * c / chunks, i1 = n * (c + 1) / chunks;
            if (i0 == i1) continue;
            const int64_t t_from = left.t[i0] - history_us;
            const size_t iw = std::lower_bound(left.t.begin(), left.t.end(), t_from) - left.t.begin();
            const size_t jw = std::lower_bound(right.t.begin(), right.t.end(), t_from) - right.t.begin();
            workers.emplace_back(match_chunk, std::cref(left), std::cref(right), std::cref(s), iw, jw, i0, i1,
                                 std::ref(out));
        }
        for (std::thread& w : workers) w.join();
    }
    auto as_array = [](const auto& v) {
        using T = typename std::decay_t<decltype(v)>::value_type;
        py::array_t<T> a(v.size());
        std::copy(v.begin(), v.end(), a.mutable_data());
        return a;
    };
    py::dict d;
    d["disparity"] = as_array(out.disparity);   // per left event, NaN = no match
    d["cost"] = as_array(out.cost);             // cost of the best disparity, 0 = perfect
    d["margin"] = as_array(out.margin);         // uniqueness margin
    d["support"] = as_array(out.support);       // recent left events in the patch
    d["status"] = as_array(out.status);         // 0 too few events, 1 high cost, 2 not unique,
                                                // 3 left-right check failed, 4 matched
    return d;
}

void add_noise_filter(py::module_& m);   // cpp/noise_filter.cpp

PYBIND11_MODULE(_evmatch, m) {
    m.doc() = "Event-by-event stereo matching (cpp/event_match.cpp) and noise filter (cpp/noise_filter.cpp)";
    add_noise_filter(m);
    m.def("match_events", &match_events, "Event-by-event matching, a disparity per left event",
          py::arg("xl"), py::arg("yl"), py::arg("onl"), py::arg("tl"),
          py::arg("xr"), py::arg("yr"), py::arg("onr"), py::arg("tr"),
          py::arg("width"), py::arg("height"), py::arg("min_disp"), py::arg("max_disp"),
          py::arg("sign"), py::arg("patch"), py::arg("max_dt_us"), py::arg("max_age_us"),
          py::arg("time_rows"), py::arg("min_events"), py::arg("max_cost"), py::arg("min_margin"),
          py::arg("lr_tol"), py::arg("threads"));
}
