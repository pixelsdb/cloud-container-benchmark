cmake_minimum_required(VERSION 3.10)
project(rocksdb_bench LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -frtti")

# RocksDB
include_directories(/usr/local/include)
link_directories(/usr/local/lib)

include(FetchContent)
FetchContent_Declare(
        googletest

        GIT_REPOSITORY https://github.com/google/googletest.git
        GIT_TAG release-1.12.1
)
FetchContent_MakeAvailable(googletest)
enable_testing()

add_executable(rocksdb_ts_test
        rocksdb_test.cc
        rocksdb_factory.cpp
)

add_executable(rocksdb_load
        rocksdb_load.cpp
        rocksdb_factory.cpp
)

target_link_libraries(rocksdb_ts_test
        gtest
        gtest_main
        rocksdb
        pthread
        z
        snappy
        lz4
        zstd
        bz2
)

target_link_libraries(rocksdb_load
        gtest
        gtest_main
        rocksdb
        pthread
        z
        snappy
        lz4
        zstd
        bz2
)

include(GoogleTest)
gtest_discover_tests(rocksdb_ts_test)
add_test(NAME rocksdb_ts_test_TESTS COMMAND rocksdb_old_ts_test)

