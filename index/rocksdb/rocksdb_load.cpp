#include <gtest/gtest.h>
#include <rocksdb/db.h>
#include <rocksdb/options.h>
#include <rocksdb/slice.h>
#include <rocksdb/utilities/options_util.h>
#include <thread>
#include <atomic>
#include <vector>
#include <iostream>

#include "config.h"
#include "rocksdb_factory.h"
#include "util.h"

using namespace rocksdb;

class RocksDBSequentialLoadTest : public ::testing::Test {
protected:
    std::unique_ptr<Config> cfg;
    std::unique_ptr<DB> db;
    std::vector<std::unique_ptr<ColumnFamilyHandle>> handles;

    void test(Preset preset)
    {
        cfg = std::make_unique<Config>(preset);
        OpenDb();
        fillSequentialData();
    }

    void TearDown() override {
        handles.clear();
        db.reset();
    }

private:
    void OpenDb() {
        Options options;
        options.create_if_missing = true;

        if (cfg->destroy_before_start_) {
            DestroyDB(cfg->db_path_, options);
        }

        // Open DB with ts_type-aware factory
        db = createRocksDB(*cfg, handles);
    }
    // Sequentially fill DB from 0 to max-1
    void fillSequentialData() {
        std::vector<std::thread> threads;
        std::atomic<long long> counter{0};
        long long timestamp = 0;
        std::string tsBuffer(8, '\0');
        const Slice& tsSlice = EncodeU64Ts(timestamp, &tsBuffer);
        for (int t = 0; t < cfg->thread_num_; ++t) {
            threads.emplace_back([this, t, &counter, timestamp, &tsSlice]()
            {
                WriteOptions wopt;
                for (int key = 0; key < cfg->id_range_; ++key) {
                    std::string k = encodeKey(*cfg, t, key, timestamp);
                    std::string v = encodeValue(key);
                    if (cfg->ts_type_ == ts_type_t::udt) {
                        db->Put(wopt, k, tsSlice, v);
                    } else {
                        db->Put(wopt, k, v);
                    }
                    counter.fetch_add(1, std::memory_order_relaxed);
                }
            }
            );
        }
        for (auto& th : threads) th.join();
        std::cout << "Total loaded: " << counter.load() << " entries" << std::endl;
    }
};


TEST_F(RocksDBSequentialLoadTest, SequentialLoadUdt10m) {
    test(Preset::Udt10m);
}

TEST_F(RocksDBSequentialLoadTest, SequentialLoadAsc10m) {
    test(Preset::Asc10m);
}

TEST_F(RocksDBSequentialLoadTest, SequentialLoadDesc10m) {
    test(Preset::Desc10m);
}

TEST_F(RocksDBSequentialLoadTest, SequentialLoadUdt1k) {
    test(Preset::Udt1k);
}

TEST_F(RocksDBSequentialLoadTest, SequentialLoadAsc1k) {
    test(Preset::Asc1k);
}

TEST_F(RocksDBSequentialLoadTest, SequentialLoadDesc1k) {
    test(Preset::Desc1k);
}

TEST(RocksDBSmallTest, UDT) {
    Preset preset = Preset::Udt1k;
    std::vector<std::unique_ptr<ColumnFamilyHandle>> handles;
    auto cfg = std::make_unique<Config>(preset);
    {
        Options options;
        options.create_if_missing = true;
        if (cfg->destroy_before_start_) {
            DestroyDB(cfg->db_path_, options);
        }
    }

    auto db = createRocksDB(*cfg, handles);

    std::string tsBuf = std::string(8, '\0');
    long long timestamp = 1761139362806988526;
    auto ts = EncodeU64Ts(timestamp, &tsBuf);

    WriteOptions wopt;
    std::string key = "abc";
    std::string value = "ray";
    db->Put(wopt, key, ts, value);

    ReadOptions ropt;
    long long timestamp2 = 1761139362806988525;
    auto ts2 = EncodeU64Ts(timestamp2, &tsBuf);
    ropt.timestamp = &ts2;
    std::string rvalue = std::string(8, '\0');
    auto s = db->Get(ropt, key, &rvalue);
    ASSERT_TRUE(s.ok());
    std::cout << rvalue << std::endl;
    handles.clear();
    db = nullptr;
}
