# NavosEdge Display GUI — Desktop Simulation Build
#
# This CMakeLists.txt builds the display GUI for desktop testing.
# It compiles with libcurl for HTTP fetching and outputs text-based
# simulation of the TFT display calls.
#
# Usage:
#   cd Hardware/display/build
#   cmake ..
#   make
#   ./navos_display_sim

cmake_minimum_required(VERSION 3.10)
project(navos_display_sim CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(CURL REQUIRED)

# Sources
set(SOURCES
    main.cpp
    gui/NavosEdgeGUI.cpp
    network/ServerClient.cpp
)

# Server configuration — override at build time with -D flags
# Example: cmake .. -DNAVOS_SERVER_URL="http://192.168.1.10:8420"
if(NOT DEFINED NAVOS_SERVER_URL)
    set(NAVOS_SERVER_URL "http://localhost:8420")
endif()

if(NOT DEFINED NAVOS_NODE_ID)
    set(NAVOS_NODE_ID "uno-q-001")
endif()

if(NOT DEFINED NAVOS_FETCH_INTERVAL_MS)
    set(NAVOS_FETCH_INTERVAL_MS "10000")
endif()

if(NOT DEFINED NAVOS_SCREEN_ROTATE_MS)
    set(NAVOS_SCREEN_ROTATE_MS "10000")
endif()

add_executable(navos_display_sim ${SOURCES})

target_compile_definitions(navos_display_sim PRIVATE
    NAVOS_SERVER_URL="${NAVOS_SERVER_URL}"
    NAVOS_NODE_ID="${NAVOS_NODE_ID}"
    NAVOS_FETCH_INTERVAL_MS=${NAVOS_FETCH_INTERVAL_MS}
    NAVOS_SCREEN_ROTATE_MS=${NAVOS_SCREEN_ROTATE_MS}
)

target_include_directories(navos_display_sim PRIVATE
    ${CMAKE_SOURCE_DIR}
)

target_link_libraries(navos_display_sim CURL::libcurl)
