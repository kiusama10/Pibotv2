cmake_minimum_required(VERSION 3.18)
project(saocb_bridge LANGUAGES CXX)

add_library(saocb_bridge SHARED
    cocos_response_bridge.cpp
    cocos_runtime_android.cpp
    fetch_user_all_hook.cpp
    jni_bridge.cpp
    request_registry.cpp
)

target_compile_features(saocb_bridge PRIVATE cxx_std_17)
target_include_directories(saocb_bridge PRIVATE .)
target_compile_options(saocb_bridge PRIVATE -fno-omit-frame-pointer)
target_link_libraries(saocb_bridge PRIVATE dl log)
