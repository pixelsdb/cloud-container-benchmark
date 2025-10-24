//
// Created by antio2 on 2025/10/21.
//

#ifndef ROCKSDB_BENCH_CONFIG_H
#define ROCKSDB_BENCH_CONFIG_H

#pragma once
#include <string>
#include <sstream>

enum class ts_type_t {
    embed_asc,
    embed_desc,
    udt
};
inline std::ostream& operator<<(std::ostream& os, ts_type_t t) {
    switch (t) {
        case ts_type_t::embed_asc:  os << "embed_asc";  break;
        case ts_type_t::embed_desc: os << "embed_desc"; break;
        case ts_type_t::udt:        os << "udt";        break;
        default:                    os << "unknown";    break;
    }
    return os;
}

enum class Preset {
    Udt10m,
    Asc10m,
    Desc10m,
    Udt1k,
    Asc1k,
    Desc1k
};

struct Config {
public:
    using scale_t = int;

    const std::string db_path_prefix = "/home/ubuntu/disk1"; // hard code
    std::string db_path_;
    int thread_num_;
    int id_range_;
    int ops_per_thread_;
    bool destroy_before_start_;
    ts_type_t ts_type_;

    Config() = delete;

    explicit Config(Preset preset)
            : Config(getScaleAndType(preset))
    {}

    Config(scale_t scale, ts_type_t ts_type) {
        thread_num_ = 16;
        ops_per_thread_ = 1000000;
        id_range_ = scale;
        destroy_before_start_ = true;
        ts_type_ = ts_type;
        std::ostringstream oss;
        oss << db_path_prefix << "/test_" << id_range_ << "_" << ts_type_;
        db_path_ = oss.str();
    }
private:
    static std::pair<scale_t, ts_type_t> getScaleAndType(Preset preset) {
        switch (preset) {
            case Preset::Udt10m:   return {10000000, ts_type_t::udt};
            case Preset::Asc10m:   return {10000000, ts_type_t::embed_asc};
            case Preset::Desc10m:  return {10000000, ts_type_t::embed_desc};
            case Preset::Udt1k:    return {1000, ts_type_t::udt};
            case Preset::Asc1k:    return {1000, ts_type_t::embed_asc};
            case Preset::Desc1k:   return {1000, ts_type_t::embed_desc};
        }
        return {0, ts_type_t::embed_asc};
    }

    explicit Config(const std::pair<scale_t, ts_type_t>& p)
            : Config(p.first, p.second)
    {}
};
#endif //ROCKSDB_BENCH_CONFIG_H
