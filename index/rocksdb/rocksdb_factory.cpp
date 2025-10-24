//
// Created by antio2 on 2025/10/21.
//



#pragma once
#include <rocksdb/db.h>
#include <rocksdb/options.h>
#include <rocksdb/slice.h>
#include <rocksdb/status.h>
#include <memory>
#include <vector>
#include <iostream>
#include "rocksdb_factory.h"
#include "config.h"
#include <rocksdb/comparator.h>
#include <rocksdb/table.h>
#include <rocksdb/filter_policy.h>
#include <rocksdb/slice_transform.h>

using namespace rocksdb;

std::unique_ptr<DB> initRocksDB(
        const Config& cfg,
        std::vector<std::unique_ptr<ColumnFamilyHandle>>& handles)
{
    Options options;
    options.create_if_missing = true;
    return createRocksDB(cfg, handles);
}

std::unique_ptr<DB> createRocksDB(
        const Config& cfg,
        std::vector<std::unique_ptr<ColumnFamilyHandle>>& handles)
{
    std::vector<std::string> existingColumnFamilies;
    Status s = DB::ListColumnFamilies(DBOptions(), cfg.db_path_, &existingColumnFamilies);

    if (!s.ok()) {
        existingColumnFamilies = {kDefaultColumnFamilyName};
    }

    bool hasDefault = false;
    for (const auto& n : existingColumnFamilies)
        if (n == kDefaultColumnFamilyName) hasDefault = true;
    if (!hasDefault)
        existingColumnFamilies.push_back(kDefaultColumnFamilyName);

    std::vector<ColumnFamilyDescriptor> descriptors;
    for (const auto& name : existingColumnFamilies) {
        ColumnFamilyOptions cfOptions;
        if (cfg.ts_type_ == ts_type_t::udt) {
            cfOptions.comparator = rocksdb::BytewiseComparatorWithU64Ts();
        } else {
        }

        if(cfg.ts_type_ == ts_type_t::embed_desc)
        {
            rocksdb::BlockBasedTableOptions table_options;
            table_options.filter_policy.reset(rocksdb::NewBloomFilterPolicy(10, false));
            table_options.whole_key_filtering = false;

            cfOptions.prefix_extractor.reset(rocksdb::NewFixedPrefixTransform(8));
            cfOptions.table_factory.reset(rocksdb::NewBlockBasedTableFactory(table_options));
        }

        cfOptions.write_buffer_size = (size_t)6 << 30;
        descriptors.emplace_back(name, cfOptions);
    }

    DBOptions dbOptions;
    dbOptions.create_if_missing = true;
    dbOptions.create_missing_column_families = true;

    DB* db = nullptr;
    std::vector<ColumnFamilyHandle*> rawHandles;
    s = DB::Open(dbOptions, cfg.db_path_, descriptors, &rawHandles, &db);
    if (!s.ok()) {
        throw std::runtime_error("Failed to open RocksDB: " + s.ToString());
    }

    handles.clear();
    for (auto* h : rawHandles)
        handles.emplace_back(h);

    std::cout << "Opened RocksDB: " << cfg.db_path_
              << ", CF=" << handles.size()
              << ", ts_type=" << (cfg.ts_type_ == ts_type_t::udt ? "UDT" : "Retina") << std::endl;

    return std::unique_ptr<DB>(db);
}
