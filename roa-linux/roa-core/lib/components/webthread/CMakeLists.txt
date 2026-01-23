cmake_minimum_required(VERSION 3.16)
project(webthread VERSION 1.0.0 LANGUAGES CXX)

# C++ Standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Compiler warnings
if(MSVC)
    add_compile_options(/W4)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Source files
set(WEBTHREAD_SOURCES
    src/cpp/WebthreadInitializer.cpp
    src/cpp/PhysicsConfigurator.cpp
    src/cpp/InputInitializer.cpp
    src/cpp/UIInitializer.cpp
    src/cpp/ComponentStarter.cpp
    src/cpp/ConfigManager.cpp
    src/cpp/fast_serializer.cpp
)

set(WEBTHREAD_HEADERS
    src/cpp/WebthreadInitializer.h
    src/cpp/PhysicsConfigurator.h
    src/cpp/InputInitializer.h
    src/cpp/UIInitializer.h
    src/cpp/ComponentStarter.h
    src/cpp/ConfigManager.h
)

# Library target
add_library(webthread STATIC ${WEBTHREAD_SOURCES} ${WEBTHREAD_HEADERS})

# Include directories
target_include_directories(webthread
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src/cpp>
        $<INSTALL_INTERFACE:include>
)

# Fast serializer executable for testing
add_executable(fast_serializer_test src/cpp/fast_serializer.cpp)

# Installation
install(TARGETS webthread fast_serializer_test
    EXPORT webthread-targets
    LIBRARY DESTINATION lib
    ARCHIVE DESTINATION lib
    RUNTIME DESTINATION bin
)

install(FILES ${WEBTHREAD_HEADERS}
    DESTINATION include/webthread
)

# Tests (if enabled)
option(BUILD_TESTS "Build tests" ON)
if(BUILD_TESTS)
    enable_testing()
    # Test targets will be added here
endif()
