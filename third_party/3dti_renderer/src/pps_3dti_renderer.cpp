#include <BinauralSpatializer/Core.h>
#include <BinauralSpatializer/Listener.h>
#include <BinauralSpatializer/SingleSourceDSP.h>
#include <Common/AudioState.h>
#include <Common/Buffer.h>
#include <Common/Transform.h>
#include <Common/Vector3.h>
#include <HRTF/HRTFCereal.h>
#if PPS_ENABLE_SOFA_READER
    #include <HRTF/HRTFFactory.h>
#endif
#include <nlohmann/json.hpp>

#define _USE_MATH_DEFINES
#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using json = nlohmann::json;

namespace {

constexpr float kDefaultHeadDiameterM = 0.18f;
constexpr float kOutputAudioPeakNormalization = 0.90f;
constexpr float kOutputLimiterPeak = 0.99f;

struct Args {
    fs::path config;
    fs::path output_dir;
    fs::path manifest;
    fs::path qc;
};

struct Point {
    double time_s = 0.0;
    double app_x = 0.0;
    double app_y = 1.0;
    double app_z = 0.0;
};

struct RenderedFile {
    fs::path path;
    std::string label;
    std::string noise_type;
    double peak = 0.0;
    bool clipping = false;
    double first_half_left_rms = 0.0;
    double first_half_right_rms = 0.0;
    double second_half_left_rms = 0.0;
    double second_half_right_rms = 0.0;
};

void usage() {
    std::cerr << "pps-3dti-renderer --config render_config.3dti.json --output-dir DIR "
                 "--manifest render_manifest.json --qc render_qc.csv\n";
}

Args parse_args(int argc, char** argv) {
    Args args;
    for (int i = 1; i < argc; ++i) {
        const std::string key = argv[i];
        if (key == "--config" && i + 1 < argc) {
            args.config = argv[++i];
        } else if (key == "--output-dir" && i + 1 < argc) {
            args.output_dir = argv[++i];
        } else if (key == "--manifest" && i + 1 < argc) {
            args.manifest = argv[++i];
        } else if (key == "--qc" && i + 1 < argc) {
            args.qc = argv[++i];
        } else if (key == "--help" || key == "-h") {
            usage();
            std::exit(0);
        } else {
            throw std::runtime_error("Unknown or incomplete argument: " + key);
        }
    }
    if (args.config.empty() || args.output_dir.empty() || args.manifest.empty() || args.qc.empty()) {
        throw std::runtime_error("Missing required arguments.");
    }
    return args;
}

std::string slurp(const fs::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) {
        throw std::runtime_error("Could not open " + path.string());
    }
    std::ostringstream buffer;
    buffer << in.rdbuf();
    return buffer.str();
}

std::string slug(std::string value) {
    for (char& c : value) {
        const bool ok = std::isalnum(static_cast<unsigned char>(c)) || c == '.' || c == '-' || c == '_';
        if (!ok) {
            c = '_';
        }
    }
    while (!value.empty() && value.front() == '_') {
        value.erase(value.begin());
    }
    while (!value.empty() && value.back() == '_') {
        value.pop_back();
    }
    return value.empty() ? "stimulus" : value;
}

fs::path resolve_from_cwd(const fs::path& path) {
    if (path.is_absolute()) {
        return path;
    }
    return fs::current_path() / path;
}

std::vector<Point> read_points(const json& config) {
    std::vector<Point> points;
    for (const auto& row : config.at("trajectory").at("samples")) {
        points.push_back(Point{
            row.at("time_s").get<double>(),
            row.at("x_m").get<double>(),
            row.at("y_m").get<double>(),
            row.at("z_m").get<double>(),
        });
    }
    if (points.empty()) {
        throw std::runtime_error("Config trajectory has no samples.");
    }
    return points;
}

Point point_at_time(const std::vector<Point>& points, double time_s) {
    auto best = std::min_element(points.begin(), points.end(), [time_s](const Point& a, const Point& b) {
        return std::abs(a.time_s - time_s) < std::abs(b.time_s - time_s);
    });
    return best == points.end() ? points.front() : *best;
}

Common::CVector3 app_to_3dti(const Point& p) {
    // PPS app convention: X right, Y front, Z up.
    // 3DTI default convention: X forward, -Y right, Z up.
    return Common::CVector3(static_cast<float>(p.app_y), static_cast<float>(-p.app_x), static_cast<float>(p.app_z));
}

std::vector<float> generate_noise(const std::string& noise_type, std::size_t samples, unsigned int seed) {
    std::mt19937 rng(seed);
    std::normal_distribution<float> normal(0.0f, 1.0f);
    std::vector<float> out(samples, 0.0f);
    const std::string type = [&] {
        std::string lowered = noise_type;
        std::transform(lowered.begin(), lowered.end(), lowered.begin(), [](unsigned char c) {
            return static_cast<char>(std::tolower(c));
        });
        return lowered;
    }();

    if (type == "pink") {
        // Paul Kellet style pink filter. Deterministic and lightweight for an offline wrapper.
        double b0 = 0.0, b1 = 0.0, b2 = 0.0, b3 = 0.0, b4 = 0.0, b5 = 0.0, b6 = 0.0;
        for (std::size_t i = 0; i < samples; ++i) {
            const double white = normal(rng);
            b0 = 0.99886 * b0 + white * 0.0555179;
            b1 = 0.99332 * b1 + white * 0.0750759;
            b2 = 0.96900 * b2 + white * 0.1538520;
            b3 = 0.86650 * b3 + white * 0.3104856;
            b4 = 0.55000 * b4 + white * 0.5329522;
            b5 = -0.7616 * b5 - white * 0.0168980;
            out[i] = static_cast<float>(b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362);
            b6 = white * 0.115926;
        }
    } else if (type == "brown") {
        float state = 0.0f;
        for (std::size_t i = 0; i < samples; ++i) {
            state = 0.997f * state + 0.04f * normal(rng);
            out[i] = state;
        }
    } else if (type == "blue") {
        float previous = normal(rng);
        for (std::size_t i = 0; i < samples; ++i) {
            const float current = normal(rng);
            out[i] = current - previous;
            previous = current;
        }
    } else {
        for (float& sample : out) {
            sample = normal(rng);
        }
    }

    float peak = 0.0f;
    for (float sample : out) {
        peak = std::max(peak, std::abs(sample));
    }
    if (peak > 0.0f) {
        for (float& sample : out) {
            sample /= peak;
        }
    }
    return out;
}

std::vector<float> tactile_track(const json& config, int sample_rate, std::size_t total_samples) {
    std::vector<float> out(total_samples, 0.0f);
    const auto& spec = config.at("tactile").at("waveform");
    const double duration_s = spec.at("duration_s").get<double>();
    const double attack_hz = spec.at("attack_frequency_hz").get<double>();
    const double decay_hz = spec.at("decay_frequency_hz").get<double>();
    const double peak_norm = spec.value("peak_normalization", 0.95);
    const std::size_t cue_samples = std::max<std::size_t>(1, static_cast<std::size_t>(std::llround(duration_s * sample_rate)));
    const std::size_t attack_samples = std::max<std::size_t>(1, std::min(cue_samples, static_cast<std::size_t>(std::llround(0.02 * sample_rate))));
    std::vector<float> cue(cue_samples, 0.0f);
    for (std::size_t i = 0; i < cue_samples; ++i) {
        const double t = static_cast<double>(i) / sample_rate;
        const double hz = i < attack_samples ? attack_hz : decay_hz;
        const double window = std::sin(M_PI * static_cast<double>(i) / std::max<std::size_t>(1, cue_samples - 1));
        cue[i] = static_cast<float>(std::sin(2.0 * M_PI * hz * t) * window * peak_norm);
    }
    for (const auto& event : config.at("tactile").at("events")) {
        const std::size_t onset = static_cast<std::size_t>(std::llround(event.at("tactile_onset_s").get<double>() * sample_rate));
        for (std::size_t i = 0; i < cue.size() && onset + i < out.size(); ++i) {
            out[onset + i] += cue[i];
        }
    }
    return out;
}

void write_u16(std::ofstream& out, std::uint16_t value) {
    out.put(static_cast<char>(value & 0xff));
    out.put(static_cast<char>((value >> 8) & 0xff));
}

void write_u32(std::ofstream& out, std::uint32_t value) {
    out.put(static_cast<char>(value & 0xff));
    out.put(static_cast<char>((value >> 8) & 0xff));
    out.put(static_cast<char>((value >> 16) & 0xff));
    out.put(static_cast<char>((value >> 24) & 0xff));
}

void write_wav_float32(const fs::path& path, const std::vector<float>& interleaved, int sample_rate, int channels) {
    std::ofstream out(path, std::ios::binary);
    if (!out) {
        throw std::runtime_error("Could not write " + path.string());
    }
    const std::uint32_t data_bytes = static_cast<std::uint32_t>(interleaved.size() * sizeof(float));
    const std::uint16_t format_size = 16;
    const std::uint16_t audio_format_ieee_float = 3;
    const std::uint16_t bits_per_sample = 32;
    const std::uint16_t block_align = static_cast<std::uint16_t>(channels * sizeof(float));
    const std::uint32_t byte_rate = static_cast<std::uint32_t>(sample_rate * block_align);

    out.write("RIFF", 4);
    write_u32(out, 4 + 8 + format_size + 8 + data_bytes);
    out.write("WAVE", 4);
    out.write("fmt ", 4);
    write_u32(out, format_size);
    write_u16(out, audio_format_ieee_float);
    write_u16(out, static_cast<std::uint16_t>(channels));
    write_u32(out, static_cast<std::uint32_t>(sample_rate));
    write_u32(out, byte_rate);
    write_u16(out, block_align);
    write_u16(out, bits_per_sample);
    out.write("data", 4);
    write_u32(out, data_bytes);
    out.write(reinterpret_cast<const char*>(interleaved.data()), data_bytes);
}

std::string pseudo_sha256_note() {
    return "native-wrapper-does-not-compute-sha256-yet";
}

double rms_range(const std::vector<float>& interleaved, int channels, int channel, std::size_t first_frame, std::size_t last_frame) {
    double sum = 0.0;
    std::size_t count = 0;
    for (std::size_t frame = first_frame; frame < last_frame; ++frame) {
        const float sample = interleaved[frame * channels + channel];
        sum += static_cast<double>(sample) * sample;
        ++count;
    }
    return count ? std::sqrt(sum / count) : 0.0;
}

RenderedFile render_one(const json& config, const json& noise, int noise_index, const Args& args) {
    const int sample_rate = config.at("source").at("sample_rate").get<int>();
    const int buffer_size = 512;
    const double duration_s = config.at("trajectory").at("total_duration_s").get<double>();
    const std::size_t total_samples = std::max<std::size_t>(1, static_cast<std::size_t>(std::llround(duration_s * sample_rate)));
    const std::size_t total_blocks = (total_samples + buffer_size - 1) / buffer_size;
    const auto points = read_points(config);
    const auto dry = generate_noise(noise.at("noise_type").get<std::string>(), total_blocks * buffer_size, config.at("source").at("seed").get<unsigned int>() + static_cast<unsigned int>(noise_index * 1009));
    const auto tactile = tactile_track(config, sample_rate, total_samples);

    Binaural::CCore core;
    core.SetAudioState(Common::TAudioStateStruct(sample_rate, buffer_size));
    core.SetHRTFResamplingStep(5);
    const auto listener_config = config.value("listener", json::object());
    const double legacy_head_diameter = config.value("study_profile", json::object())
                                            .value("reference_parameters", json::object())
                                            .value("head_diameter_m", kDefaultHeadDiameterM);
    double head_radius_config = listener_config.value("head_radius_m", 0.0);
    if (head_radius_config <= 0.0) {
        head_radius_config = listener_config.value("head_diameter_m", legacy_head_diameter) / 2.0;
    }
    const float head_radius = static_cast<float>(head_radius_config > 0.0 ? head_radius_config : kDefaultHeadDiameterM / 2.0f);
    auto listener = core.CreateListener(head_radius);
    Common::CTransform listener_transform;
    listener_transform.SetPosition(Common::CVector3(0.0f, 0.0f, 0.0f));
    listener->SetListenerTransform(listener_transform);

    bool specified_delays = false;
    if (config.at("source").contains("hrtf_3dti_file") && !config.at("source").at("hrtf_3dti_file").get<std::string>().empty()) {
        const fs::path hrtf_path = resolve_from_cwd(config.at("source").at("hrtf_3dti_file").get<std::string>());
        if (!HRTF::CreateFrom3dti(hrtf_path.string(), listener)) {
            throw std::runtime_error("3DTI failed to load preconverted HRTF cache: " + hrtf_path.string());
        }
    } else {
#if PPS_ENABLE_SOFA_READER
        const fs::path sofa_path = resolve_from_cwd(config.at("source").at("sofa_file").get<std::string>());
        if (!HRTF::CreateFromSofa(sofa_path.string(), listener, specified_delays)) {
            throw std::runtime_error("3DTI failed to load SOFA HRTF: " + sofa_path.string());
        }
#else
        throw std::runtime_error(
            "This native wrapper was built without PPS_ENABLE_SOFA_READER. "
            "Provide source.hrtf_3dti_file in the render config.");
#endif
    }
    listener->EnableCustomizedITD();

    auto source = core.CreateSingleSourceDSP();
    source->SetSpatializationMode(Binaural::TSpatializationMode::HighQuality);
    source->EnableInterpolation();
    source->EnableAnechoicProcess();
    source->EnableDistanceAttenuationAnechoic();
    source->EnableDistanceAttenuationSmoothingAnechoic();
    source->EnableNearFieldEffect();
    source->EnablePropagationDelay();
    source->DisableReverbProcess();

    std::vector<float> interleaved(total_samples * 3, 0.0f);
    CMonoBuffer<float> in(buffer_size);
    CMonoBuffer<float> left(buffer_size);
    CMonoBuffer<float> right(buffer_size);

    for (std::size_t block = 0; block < total_blocks; ++block) {
        const std::size_t frame0 = block * buffer_size;
        const double center_time = (static_cast<double>(frame0) + buffer_size / 2.0) / sample_rate;
        Common::CTransform source_transform;
        source_transform.SetPosition(app_to_3dti(point_at_time(points, center_time)));
        source->SetSourceTransform(source_transform);

        for (int i = 0; i < buffer_size; ++i) {
            in[static_cast<std::size_t>(i)] = dry[frame0 + static_cast<std::size_t>(i)] * noise.value("gain", 1.0f);
        }
        source->SetBuffer(in);
        source->ProcessAnechoic(left, right);

        for (int i = 0; i < buffer_size && frame0 + static_cast<std::size_t>(i) < total_samples; ++i) {
            const std::size_t frame = frame0 + static_cast<std::size_t>(i);
            interleaved[frame * 3 + 0] = left[static_cast<std::size_t>(i)];
            interleaved[frame * 3 + 1] = right[static_cast<std::size_t>(i)];
            interleaved[frame * 3 + 2] = tactile[frame];
        }
    }

    float audio_peak = 0.0f;
    for (std::size_t frame = 0; frame < total_samples; ++frame) {
        audio_peak = std::max(audio_peak, std::abs(interleaved[frame * 3 + 0]));
        audio_peak = std::max(audio_peak, std::abs(interleaved[frame * 3 + 1]));
    }
    if (audio_peak > 0.0f) {
        const float audio_gain = kOutputAudioPeakNormalization / audio_peak;
        for (std::size_t frame = 0; frame < total_samples; ++frame) {
            interleaved[frame * 3 + 0] *= audio_gain;
            interleaved[frame * 3 + 1] *= audio_gain;
        }
    }

    float peak = 0.0f;
    for (float sample : interleaved) {
        peak = std::max(peak, std::abs(sample));
    }
    if (peak > kOutputLimiterPeak) {
        const float gain = kOutputLimiterPeak / peak;
        for (float& sample : interleaved) {
            sample *= gain;
        }
        peak = kOutputLimiterPeak;
    }
    const bool clipping = peak >= 1.0f;

    const std::size_t midpoint = total_samples / 2;
    const double first_left = rms_range(interleaved, 3, 0, 0, midpoint);
    const double first_right = rms_range(interleaved, 3, 1, 0, midpoint);
    const double second_left = rms_range(interleaved, 3, 0, midpoint, total_samples);
    const double second_right = rms_range(interleaved, 3, 1, midpoint, total_samples);

    const std::string label = noise.at("label").get<std::string>();
    fs::path wav_path = args.output_dir / ("looming_" + slug(label) + ".wav");
    write_wav_float32(wav_path, interleaved, sample_rate, 3);

    return RenderedFile{
        wav_path,
        label,
        noise.at("noise_type").get<std::string>(),
        peak,
        clipping,
        first_left,
        first_right,
        second_left,
        second_right,
    };
}

void write_qc(const fs::path& path, const json& config, const std::vector<RenderedFile>& files) {
    std::ofstream out(path);
    out << "status,noise_label,noise_type,duration_s,sample_rate,channels,tactile_events,tactile_channel,"
           "peak_dbfs,clipping,hrir_positions_used,first_half_left_rms,first_half_right_rms,"
           "second_half_left_rms,second_half_right_rms,wav_sha256,message\n";
    for (const auto& file : files) {
        const double dbfs = file.peak > 0.0 ? 20.0 * std::log10(file.peak) : -std::numeric_limits<double>::infinity();
        out << "rendered_3dti,"
            << '"' << file.label << '"' << ','
            << file.noise_type << ','
            << config.at("trajectory").at("total_duration_s").get<double>() << ','
            << config.at("source").at("sample_rate").get<int>() << ','
            << 3 << ','
            << config.at("tactile").at("events").size() << ','
            << 2 << ','
            << std::fixed << std::setprecision(6) << dbfs << ','
            << (file.clipping ? "true" : "false") << ','
            << "" << ','
            << std::fixed << std::setprecision(9) << file.first_half_left_rms << ','
            << std::fixed << std::setprecision(9) << file.first_half_right_rms << ','
            << std::fixed << std::setprecision(9) << file.second_half_left_rms << ','
            << std::fixed << std::setprecision(9) << file.second_half_right_rms << ','
            << pseudo_sha256_note() << ','
            << "\"Rendered by native 3DTI wrapper\"\n";
    }
}

void write_manifest(const fs::path& path, const json& config, const std::vector<RenderedFile>& files) {
    json manifest;
    manifest["schema"] = "pps-render-manifest.v1";
    manifest["status"] = "rendered_3dti";
    manifest["render_engine"] = "native-3dti";
    manifest["message"] = "Rendered by pps-3dti-renderer using the pinned 3DTI AudioToolkit source snapshot.";
    manifest["renderer"] = config.at("renderer");
    manifest["listener"] = config.value("listener", json::object());
    manifest["source"] = config.at("source");
    manifest["study_profile"] = config.value("study_profile", json::object());
    manifest["tactile_event_count"] = config.at("tactile").at("events").size();
    manifest["wav_outputs"] = json::array();
    for (const auto& file : files) {
        manifest["wav_outputs"].push_back(
            {
                {"path", file.path.string()},
                {"sha256", pseudo_sha256_note()},
            });
    }
    std::ofstream out(path);
    out << std::setw(2) << manifest << "\n";
}

}  // namespace

int main(int argc, char** argv) {
    try {
        const Args args = parse_args(argc, argv);
        fs::create_directories(args.output_dir);
        const json config = json::parse(slurp(args.config));
        if (config.value("schema", "") != "pps-3dti-render-config.v1") {
            throw std::runtime_error("Unsupported render config schema.");
        }
        std::vector<RenderedFile> files;
        int index = 0;
        for (const auto& noise : config.at("source").at("noises")) {
            files.push_back(render_one(config, noise, index++, args));
        }
        write_qc(args.qc, config, files);
        write_manifest(args.manifest, config, files);
        return 0;
    } catch (const std::exception& exc) {
        std::cerr << exc.what() << "\n";
        usage();
        return 1;
    }
}
