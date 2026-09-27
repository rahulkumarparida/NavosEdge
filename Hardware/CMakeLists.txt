cmake_minimum_required(VERSION 3.10)
project(navos_hardware_bridge CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CURL REQUIRED)

include_directories(
    ${CMAKE_SOURCE_DIR}/include
    ${CMAKE_SOURCE_DIR}/third_party
)

file(GLOB SOURCES "src/*.cpp")

add_executable(navos_hardware_bridge ${SOURCES})
target_link_libraries(navos_hardware_bridge CURL::libcurl)

add_executable(navos_hardware_bridge_test tests/test_bridge.cpp)
target_link_libraries(navos_hardware_bridge_test CURL::libcurl)
