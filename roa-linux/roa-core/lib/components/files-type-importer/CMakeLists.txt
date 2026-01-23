cmake_minimum_required(VERSION 3.16)
project(files_type_importer VERSION 1.0.0)

# Find ROS2 dependencies (if building as ROS2 package)
find_package(ament_cmake QUIET)

if(ament_cmake_FOUND)
    # ROS2 package build
    find_package(ament_cmake_python REQUIRED)
    find_package(rclpy REQUIRED)
    
    # Python package installation
    ament_python_install_package(${PROJECT_NAME}
        PACKAGE_DIR src/python
    )
    
    # Install config files
    install(DIRECTORY Config/
        DESTINATION share/${PROJECT_NAME}/config
    )
    
    # Install examples
    install(DIRECTORY examples/
        DESTINATION share/${PROJECT_NAME}/examples
    )
    
    # Tests
    if(BUILD_TESTING)
        find_package(ament_lint_auto REQUIRED)
        ament_lint_auto_find_test_dependencies()
        
        find_package(ament_cmake_pytest REQUIRED)
        ament_add_pytest_test(fti_tests tests/
            TIMEOUT 60
        )
    endif()
    
    ament_package()
else()
    # Standalone CMake build
    message(STATUS "Building as standalone package")
    
    # Install Python files
    install(DIRECTORY src/python/
        DESTINATION lib/python/files_type_importer
        FILES_MATCHING PATTERN "*.py"
    )
    
    # Install config and examples
    install(DIRECTORY Config/ DESTINATION etc/files_type_importer/config)
    install(DIRECTORY examples/ DESTINATION share/files_type_importer/examples)
endif()
