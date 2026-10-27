// Included inside the wrapper's anonymous namespace. V2 consumes Rust-prepared
// PCM; it never regenerates noise, normalizes, limits, or mixes tactile samples.

constexpr std::size_t kMaxPreparedFrames = 192000 * 60;

void exact_keys(const json& value, std::initializer_list<const char*> keys) {
    if (!value.is_object() || value.size() != keys.size()) {
        throw std::runtime_error("Unexpected prepared spatializer fields.");
    }
    for (const char* key : keys) { if (!value.contains(key)) { throw std::runtime_error("Missing prepared spatializer field."); } }
}

std::string sha256_bytes(const unsigned char* bytes, std::size_t length) {
#ifdef _WIN32
    unsigned char digest[32] = {};
    if (length > std::numeric_limits<ULONG>::max()
        || BCryptHash(BCRYPT_SHA256_ALG_HANDLE, nullptr, 0,
            const_cast<unsigned char*>(bytes), static_cast<ULONG>(length), digest, sizeof(digest)) < 0) {
        throw std::runtime_error("SHA-256 failed.");
    }
    std::ostringstream hex;
    for (unsigned char byte : digest) { hex << std::hex << std::setw(2) << std::setfill('0') << static_cast<unsigned>(byte); }
    return hex.str();
#else
    throw std::runtime_error("Prepared spatializer SHA-256 currently requires the Windows build.");
#endif
}

std::string sha256_resource(const fs::path& path) {
#ifdef _WIN32
    BCRYPT_HASH_HANDLE hash = nullptr;
    if (BCryptCreateHash(BCRYPT_SHA256_ALG_HANDLE, &hash, nullptr, 0, nullptr, 0, 0) < 0) { throw std::runtime_error("Resource hash creation failed."); }
    std::ifstream input(path, std::ios::binary);
    unsigned char bytes[65536];
    bool ok = static_cast<bool>(input);
    while (ok && input) {
        input.read(reinterpret_cast<char*>(bytes), sizeof(bytes));
        const auto count = input.gcount();
        if (count > 0) { ok = BCryptHashData(hash, bytes, static_cast<ULONG>(count), 0) >= 0; }
    }
    unsigned char digest[32] = {};
    ok = ok && input.eof() && BCryptFinishHash(hash, digest, sizeof(digest), 0) >= 0;
    BCryptDestroyHash(hash);
    if (!ok) { throw std::runtime_error("Resource SHA-256 failed."); }
    std::ostringstream hex;
    for (const auto byte : digest) { hex << std::hex << std::setw(2) << std::setfill('0') << static_cast<unsigned>(byte); }
    return hex.str();
#else
    throw std::runtime_error("Prepared spatializer SHA-256 currently requires the Windows build.");
#endif
}

Point prepared_position(const json& position) {
    exact_keys(position, {"x_m", "y_m", "z_m"});
    Point p{0.0, position.at("x_m").get<double>(), position.at("y_m").get<double>(), position.at("z_m").get<double>()};
    const double distance_squared = p.app_x * p.app_x + p.app_y * p.app_y + p.app_z * p.app_z;
    if (!std::isfinite(distance_squared) || std::abs(p.app_x) > 100 || std::abs(p.app_y) > 100
        || std::abs(p.app_z) > 100 || distance_squared < 0.0001) { throw std::runtime_error("Invalid prepared source position."); }
    return p;
}

struct PreparedMotion {
    Point start;
    Point end;
    double hold;
    double movement;
    bool polar = false;
    double radius_start = 0, radius_end = 0, azimuth_start = 0, azimuth_end = 0, elevation = 0;
    double minimum_distance() const {
        if (polar) { return std::min(radius_start, radius_end); }
        const double dx = end.app_x - start.app_x, dy = end.app_y - start.app_y, dz = end.app_z - start.app_z;
        const double length_squared = dx * dx + dy * dy + dz * dz;
        const double f = length_squared > 0 ? std::clamp(-(start.app_x * dx + start.app_y * dy + start.app_z * dz) / length_squared, 0.0, 1.0) : 0.0;
        const Point p = at(hold + f * movement);
        return std::sqrt(p.app_x * p.app_x + p.app_y * p.app_y + p.app_z * p.app_z);
    }
    Point at(double time) const {
        const double fraction = movement > 0 ? std::clamp((time - hold) / movement, 0.0, 1.0) : 0.0;
        if (polar) {
            const double radius = radius_start + fraction * (radius_end - radius_start);
            const double az = (azimuth_start + fraction * (azimuth_end - azimuth_start)) * M_PI / 180.0;
            const double el = elevation * M_PI / 180.0;
            return Point{time, radius * std::cos(el) * std::sin(az), radius * std::cos(el) * std::cos(az), radius * std::sin(el)};
        }
        return Point{time, start.app_x + fraction * (end.app_x - start.app_x),
            start.app_y + fraction * (end.app_y - start.app_y), start.app_z + fraction * (end.app_z - start.app_z)};
    }
};

PreparedMotion prepared_motion(const json& trajectory, double duration) {
    const auto kind = trajectory.at("kind").get<std::string>();
    if (kind == "fixed") {
        exact_keys(trajectory, {"kind", "position"});
        const Point p = prepared_position(trajectory.at("position"));
        return PreparedMotion{p, p, 0.0, 0.0};
    }
    PreparedMotion result{};
    if (kind == "linear") {
        exact_keys(trajectory, {"kind", "start", "end", "pre_hold_s", "movement_duration_s"});
        result.start = prepared_position(trajectory.at("start")); result.end = prepared_position(trajectory.at("end"));
    } else if (kind == "polar") {
        exact_keys(trajectory, {"kind", "start_radius_m", "end_radius_m", "azimuth_start_deg", "azimuth_end_deg", "elevation_deg", "pre_hold_s", "movement_duration_s"});
        result.polar = true;
        result.radius_start = trajectory.at("start_radius_m").get<double>(); result.radius_end = trajectory.at("end_radius_m").get<double>();
        result.azimuth_start = trajectory.at("azimuth_start_deg").get<double>(); result.azimuth_end = trajectory.at("azimuth_end_deg").get<double>();
        result.elevation = trajectory.at("elevation_deg").get<double>();
        for (const double value : {result.radius_start, result.radius_end, result.azimuth_start, result.azimuth_end, result.elevation}) {
            if (!std::isfinite(value)) { throw std::runtime_error("Nonfinite polar motion."); }
        }
        if (result.radius_start < 0.01 || result.radius_start > 100 || result.radius_end < 0.01 || result.radius_end > 100
            || std::abs(result.azimuth_start) > 360 || std::abs(result.azimuth_end) > 360 || std::abs(result.elevation) > 90) {
            throw std::runtime_error("Invalid polar motion.");
        }
    } else { throw std::runtime_error("Unsupported prepared motion."); }
    result.hold = trajectory.at("pre_hold_s").get<double>(); result.movement = trajectory.at("movement_duration_s").get<double>();
    if (!std::isfinite(result.hold) || !std::isfinite(result.movement) || result.hold < 0
        || result.movement <= 0 || result.hold + result.movement > duration + 0.5 / 192000.0) {
        throw std::runtime_error("Invalid prepared motion timing.");
    }
    if (result.minimum_distance() < 0.01) {
        throw std::runtime_error("Prepared source path crosses listener origin.");
    }
    return result;
}

void spatialize_prepared(const json& config, const Args& args) {
    exact_keys(config, {"schema", "sample_rate_hz", "frames", "dry_source", "trajectory", "spatialization", "hrtf"});
    const int rate = config.at("sample_rate_hz").get<int>();
    if (!config.at("frames").is_number_unsigned()) { throw std::runtime_error("Prepared frame count must be a positive integer."); }
    const auto frames = config.at("frames").get<std::size_t>();
    if (rate < 8000 || rate > 192000 || frames == 0 || frames > kMaxPreparedFrames || frames > static_cast<std::size_t>(rate) * 60) {
        throw std::runtime_error("Prepared render exceeds resource limits.");
    }
    const auto& dry_config = config.at("dry_source");
    exact_keys(dry_config, {"path", "sha256", "algorithm"});
    if (dry_config.at("path") != "dry.f32" || dry_config.at("algorithm") != "rand-0.8.8-std-rng-box-muller.v1") {
        throw std::runtime_error("Unsupported prepared source path or algorithm.");
    }
    const auto dry_path = args.config.parent_path() / "dry.f32";
    if (fs::file_size(dry_path) != frames * sizeof(float)) { throw std::runtime_error("Prepared PCM byte count mismatch."); }
    std::vector<float> dry(frames);
    std::ifstream input(dry_path, std::ios::binary);
    input.read(reinterpret_cast<char*>(dry.data()), static_cast<std::streamsize>(frames * sizeof(float)));
    if (!input || std::any_of(dry.begin(), dry.end(), [](float v) { return !std::isfinite(v); })) {
        throw std::runtime_error("Prepared PCM is truncated or nonfinite.");
    }
    const auto input_hash = sha256_bytes(reinterpret_cast<const unsigned char*>(dry.data()), dry.size() * sizeof(float));
    if (input_hash != dry_config.at("sha256")) { throw std::runtime_error("Prepared PCM SHA-256 mismatch."); }
    const auto motion = prepared_motion(config.at("trajectory"), static_cast<double>(frames) / rate);
    const auto& options = config.at("spatialization");
    exact_keys(options, {"distance_attenuation", "near_field", "propagation_delay", "far_distance_filter", "head_radius_m", "normalization", "output_channels"});
    if (options.at("normalization") != "none" || options.at("output_channels") != 2 || options.at("far_distance_filter") != false) {
        throw std::runtime_error("Prepared spatializer requires unnormalized stereo output.");
    }
    const double head_radius = options.at("head_radius_m").get<double>();
    if (!std::isfinite(head_radius) || head_radius < 0.04 || head_radius > 0.15) { throw std::runtime_error("Invalid head radius."); }
    if (motion.minimum_distance() <= head_radius) { throw std::runtime_error("Prepared source enters listener head."); }
    const bool attenuation = options.at("distance_attenuation").get<bool>();
    const bool near_field = options.at("near_field").get<bool>();
    if (near_field) { throw std::runtime_error("Near-field correction requires a verified ILD asset; unsupported by prepared v2."); }
    const bool propagation = options.at("propagation_delay").get<bool>();
    const auto& hrtf = config.at("hrtf");
    exact_keys(hrtf, {"path", "format"});
    const auto hrtf_path = resolve_from_cwd(hrtf.at("path").get<std::string>());
    if (fs::file_size(hrtf_path) > 512 * 1024 * 1024) { throw std::runtime_error("HRTF exceeds 512 MiB limit."); }
    const auto hrtf_hash = sha256_resource(hrtf_path);

    constexpr int block_size = 512;
    Binaural::CCore core;
    core.SetAudioState(Common::TAudioStateStruct(rate, block_size));
    core.SetHRTFResamplingStep(5);
    auto listener = core.CreateListener(static_cast<float>(head_radius));
    Common::CTransform listener_transform;
    listener_transform.SetPosition(Common::CVector3(0, 0, 0));
    listener->SetListenerTransform(listener_transform);
    bool specified_delays = false;
    bool loaded = false;
    if (hrtf.at("format") == "three_dti") {
        if (HRTF::GetSampleRateFrom3dti(hrtf_path.string()) != rate) { throw std::runtime_error("HRTF sample rate mismatch; explicit resampling is required."); }
        loaded = HRTF::CreateFrom3dti(hrtf_path.string(), listener);
    } else if (hrtf.at("format") == "sofa") {
#if PPS_ENABLE_SOFA_READER
        if (HRTF::GetSampleRateFromSofa(hrtf_path.string()) != rate) { throw std::runtime_error("HRTF sample rate mismatch; explicit resampling is required."); }
        loaded = HRTF::CreateFromSofa(hrtf_path.string(), listener, specified_delays);
#else
        throw std::runtime_error("This build requires preconverted HRTF input.");
#endif
    }
    if (!loaded) { throw std::runtime_error("Failed to load prepared HRTF asset."); }
    listener->EnableCustomizedITD();
    auto source = core.CreateSingleSourceDSP();
    source->SetSpatializationMode(Binaural::TSpatializationMode::HighQuality);
    source->EnableInterpolation();
    source->EnableAnechoicProcess();
    source->DisableFarDistanceEffect();
    if (attenuation) { source->EnableDistanceAttenuationAnechoic(); source->EnableDistanceAttenuationSmoothingAnechoic(); }
    else { source->DisableDistanceAttenuationAnechoic(); }
    if (near_field) { source->EnableNearFieldEffect(); } else { source->DisableNearFieldEffect(); }
    if (propagation) { source->EnablePropagationDelay(); } else { source->DisablePropagationDelay(); }
    source->DisableReverbProcess();

    std::vector<float> stereo(frames * 2, 0);
    CMonoBuffer<float> in(block_size), left(block_size), right(block_size);
    for (std::size_t first = 0; first < frames; first += block_size) {
        Common::CTransform transform;
        transform.SetPosition(app_to_3dti(motion.at((static_cast<double>(first) + block_size / 2.0) / rate)));
        source->SetSourceTransform(transform);
        for (int i = 0; i < block_size; ++i) { in[i] = first + i < frames ? dry[first + i] : 0.0f; }
        source->SetBuffer(in);
        source->ProcessAnechoic(left, right);
        for (int i = 0; i < block_size && first + i < frames; ++i) {
            if (!std::isfinite(left[i]) || !std::isfinite(right[i])) { throw std::runtime_error("Spatializer returned nonfinite PCM."); }
            stereo[2 * (first + i)] = left[i];
            stereo[2 * (first + i) + 1] = right[i];
        }
    }
    const fs::path output = args.output_dir / "stereo.wav";
    write_wav_float32(output, stereo, rate, 2);
    const auto pcm_hash = sha256_bytes(reinterpret_cast<const unsigned char*>(stereo.data()), stereo.size() * sizeof(float));
    float peak = 0;
    for (const auto sample : stereo) { peak = std::max(peak, std::abs(sample)); }
    json report = {{"schema", "pps-3dti-spatialized.v2"}, {"source_sha256", input_hash}, {"stereo_pcm_sha256", pcm_hash},
        {"output", "stereo.wav"}, {"sample_rate_hz", rate}, {"frames", frames}, {"channels", 2}, {"peak", peak},
        {"spatialization", options}, {"motion", config.at("trajectory")}, {"block_size_frames", block_size},
        {"motion_sampling", "declared-coordinate-interpolation-at-block-center"}, {"tail_policy", "truncate-at-requested-frames"},
        {"physical_spl_qualified", false}, {"source_algorithm", dry_config.at("algorithm")}, {"customized_itd", true}};
    report["attenuation_reference_distance_m"] = DISTANCE_MODEL_THRESHOLD_NEAR;
    report["attenuation_db_per_double_distance"] = core.GetMagnitudes().GetAnechoicDistanceAttenuation();
    report["toolkit_commit"] = "6bfee08705675308a8c348b4c3a4d582586d2f99";
    report["hrtf_sha256"] = hrtf_hash;
    report["hrtf_format"] = hrtf.at("format");
    std::ofstream manifest(args.manifest);
    manifest << report.dump(2) << '\n'; manifest.flush();
    std::ofstream qc(args.qc);
    qc << "frames,channels,peak,distance_attenuation,normalization\n" << frames << ",2," << std::setprecision(9)
        << peak << ',' << (attenuation ? "true" : "false") << ",none\n"; qc.flush();
    if (!manifest || !qc) { throw std::runtime_error("Failed writing spatializer evidence."); }
}
