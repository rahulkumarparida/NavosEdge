cmake_minimum_required(VERSION 3.10)
project(navos_hardware_bridge CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CURL REQUIRED)

include_directories(
    ${CMAKE_SOURCE_DIR}/include
    ${CMAKE_SOURCE_DIR}/third_party
    ${CMAKE_SOURCE_DIR}/display
)

set(SOURCES
    src/main.cpp
)

add_executable(navos_hardware_bridge ${SOURCES})
target_link_libraries(navos_hardware_bridge CURL::libcurl)

if(EXISTS "${CMAKE_SOURCE_DIR}/tests/test_bridge.cpp")
    add_executable(test_bridge tests/test_bridge.cpp)
    target_link_libraries(test_bridge CURL::libcurl)
endif()
