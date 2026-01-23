cmake_minimum_required(VERSION 3.16)
project(roc_control VERSION 1.0.0 LANGUAGES CXX)

# C++ Standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find ROS2 dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(control_msgs REQUIRED)
find_package(controller_interface REQUIRED)
find_package(hardware_interface REQUIRED)

# C++ source files (if any exist in src/cpp)
if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp)
    file(GLOB_RECURSE CPP_SOURCES src/cpp/*.cpp)
    file(GLOB_RECURSE CPP_HEADERS src/cpp/*.h src/cpp/*.hpp)
    
    if(CPP_SOURCES)
        # Library target
        add_library(roc_control SHARED ${CPP_SOURCES} ${CPP_HEADERS})
        
        # Include directories
        target_include_directories(roc_control
            PUBLIC
                $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/src/cpp>
                $<INSTALL_INTERFACE:include>
        )
        
        # Link ROS2 dependencies
        ament_target_dependencies(roc_control
            rclcpp
            std_msgs
            geometry_msgs
            sensor_msgs
            control_msgs
            controller_interface
            hardware_interface
        )
        
        # Installation
        install(TARGETS roc_control
            EXPORT roc_control-targets
            LIBRARY DESTINATION lib
            ARCHIVE DESTINATION lib
            RUNTIME DESTINATION bin
        )
        
        install(FILES ${CPP_HEADERS}
            DESTINATION include/roc_control
        )
    endif()
endif()

# Python package installation
ament_python_install_package(${PROJECT_NAME}
    PACKAGE_DIR src/python
)

# Install launch files
install(DIRECTORY launch/
    DESTINATION share/${PROJECT_NAME}/launch
    PATTERN "*.launch.py"
)

# Install config files
install(DIRECTORY Config/
    DESTINATION share/${PROJECT_NAME}/config
)

# Tests (if enabled)
if(BUILD_TESTING)
    find_package(ament_lint_auto REQUIRED)
    ament_lint_auto_find_test_dependencies()
    
    find_package(ament_cmake_pytest REQUIRED)
    ament_add_pytest_test(roc_tests tests/
        TIMEOUT 60
    )
endif()

ament_package()
