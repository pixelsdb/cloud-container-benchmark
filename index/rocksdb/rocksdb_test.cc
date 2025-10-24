#include <gtest/gtest.h>
#include <rocksdb/db.h>
#include <rocksdb/options.h>
#include <rocksdb/slice.h>
#include <rocksdb/utilities/options_util.h>
#include <thread>
#include <atomic>
#include <random>
#include <vector>
#include <iostream>

#include "config.h"
#include "rocksdb_factory.h"
#include "util.h"

using namespace rocksdb;

class RocksDBPerfTest : public ::testing::Test {
protected:
    std::unique_ptr<Config> cfg;
    std::vector<std::unique_ptr<ColumnFamilyHandle>> handles;
    std::unique_ptr<DB> db;
    void test(Preset preset)
    {
        cfg = std::make_unique<Config>(preset);
        db = initRocksDB(*cfg, handles);

        std::cerr << "Start update test" << std::endl;
        std::atomic<long long> totalOps = 0;
        auto start = std::chrono::high_resolution_clock::now();

        std::vector<std::thread> threads;
        for (int i = 0; i < cfg->thread_num_; ++i) {
            threads.emplace_back(&RocksDBPerfTest::threadWorker, this, i, std::ref(totalOps));
        }

        for (auto& t : threads) t.join();

        auto end = std::chrono::high_resolution_clock::now();
        double sec = std::chrono::duration<double>(end - start).count();

        std::cout << "Total ops: " << totalOps
                  << ", time: " << sec << "s, throughput: "
                  << (long long)(totalOps / sec) << " ops/s" << std::endl;

        ASSERT_GT(totalOps, 0);
    }

    void TearDown() override {
        handles.clear();
        db.reset();
    }
    
    long long getUniqueRowId(int indexId, int key, long long timestamp) {
        ReadOptions ropt;
        std::string val_str(8, '\0');
        std::string k = encodeKey(*cfg, indexId, key, timestamp);
        std::string ts_buf(8, '\0');
        switch (cfg->ts_type_) {
            case ts_type_t::embed_asc:
            {
                std::unique_ptr<Iterator> it(db->NewIterator(ropt));
                it->SeekForPrev(k);
                if (!it->Valid()) return -1;

                const Slice val = it->value();
                long long rowId;
                memcpy(&rowId, val.data(), sizeof(rowId));
                return rowId;
            }
            case ts_type_t::embed_desc:
            {
                ropt.prefix_same_as_start = true;
                std::unique_ptr<Iterator> it(db->NewIterator(ropt));
                it->Seek(k);
                if (!it->Valid()) return -1;

                const Slice val = it->value();
                long long rowId;
                memcpy(&rowId, val.data(), sizeof(rowId));
                return rowId;
            }
            case ts_type_t::udt:
            {
                Slice tsSlice = EncodeU64Ts(timestamp, &ts_buf);
                ropt.timestamp = &tsSlice;
                Status s = db->Get(ropt, k, &val_str);
                if (!s.ok()) {
                    if (s.IsNotFound())
                    {
                        return -1;
                    }
                    std::cerr << "DB Get failed: " << s.ToString() << std::endl;
                    return -1;
                }
                long long rowId;
                memcpy(&rowId, val_str.data(), sizeof(rowId));
                return rowId;
            }
        }
    }

public:
    void threadWorker(int indexId, std::atomic<long long>& counter) {
        std::mt19937_64 rng(std::random_device{}());

        for (int i = 0; i < cfg->ops_per_thread_; ++i) {
            int key = i % cfg->id_range_;
            uint64_t ts = std::chrono::system_clock::now().time_since_epoch().count();
            long long oldRow = getUniqueRowId(indexId, key, ts);
            ASSERT_GE(oldRow, 0);
            long long newRow = (oldRow == -1) ? rng() : oldRow + 1;
            std::string k = encodeKey(*cfg, indexId, key, ts);
            std::string v = encodeValue(newRow);
            WriteOptions wopt;
            if (cfg->ts_type_ == ts_type_t::udt) {
                std::string ts_buf;
                Slice tsSlice = EncodeU64Ts(ts, &ts_buf);
                db->Put(wopt, k, tsSlice, v);
            } else {
                db->Put(wopt, k, v);
            }
            counter.fetch_add(1, std::memory_order_relaxed);
        }
    }
};

TEST_F(RocksDBPerfTest, MultiThreadPerf_Udt10m) {
    test(Preset::Udt10m);
}

TEST_F(RocksDBPerfTest, MultiThreadPerf_Asc10m) {
    test(Preset::Asc10m);
}

TEST_F(RocksDBPerfTest, MultiThreadPerf_Desc10m) {
    test(Preset::Desc10m);
}

TEST_F(RocksDBPerfTest, MultiThreadPerf_Udt1k) {
    test(Preset::Udt1k);
}

TEST_F(RocksDBPerfTest, MultiThreadPerf_Asc1k) {
    test(Preset::Asc1k);
}

TEST_F(RocksDBPerfTest, MultiThreadPerf_Desc1k) {
    test(Preset::Desc1k);
}
