//
// Created by antio2 on 2025/10/21.
//

#ifndef ROCKSDB_BENCH_UTIL_H
#define ROCKSDB_BENCH_UTIL_H
#include <rocksdb/slice.h>
#include <string>

std::string encodeKey(Config cfg, int indexId, int key, long long timestamp) {
    ts_type_t ts_type = cfg.ts_type_;
    if (ts_type == ts_type_t::embed_asc) {
        std::string s(4 + 4 + 8, '\0');
        memcpy(&s[0], &indexId, 4);
        memcpy(&s[4], &key, 4);
        memcpy(&s[8], &timestamp, 8);
        return s;
    } else if (ts_type == ts_type_t::udt) {
        // UDT key format: indexId(4) + key(4) + timestamp_udt(8)
        std::string s(4 + 4, '\0');
        memcpy(&s[0], &indexId, 4);
        memcpy(&s[4], &key, 4);
        return s;
    } else if (ts_type == ts_type_t::embed_desc)
    {
        long long new_ts = LONG_LONG_MAX - timestamp;
        std::string s(4 + 4 + 8, '\0');
        memcpy(&s[0], &indexId, 4);
        memcpy(&s[4], &key, 4);
        memcpy(&s[8], &new_ts, 8);
        return s;
    }
    return {};
}

std::string encodeValue(long long rowId) {
    std::string s(8, '\0');
    memcpy(&s[0], &rowId, 8);
    return s;
}

#endif //ROCKSDB_BENCH_UTIL_H
