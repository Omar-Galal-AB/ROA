cmake_minimum_required(VERSION 3.8)
project(communication_center)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# Find dependencies
find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rclpy REQUIRED)
find_package(std_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

# Generate messages and services
rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/WorkArea.msg"
  "msg/ProximityAlert.msg"
  "msg/TaskCoordination.msg"
  "srv/CoordinateTask.srv"
  "srv/ReserveArea.srv"
  "srv/QueryProximity.srv"
  DEPENDENCIES std_msgs geometry_msgs
)

# Install Python modules
ament_python_install_package(${PROJECT_NAME}
  PACKAGE_DIR src/python
)

# Install Python executables
install(PROGRAMS
  src/python/comc_node.py
  DESTINATION lib/${PROJECT_NAME}
)

# Install launch files
install(DIRECTORY
  launch
  DESTINATION share/${PROJECT_NAME}/
)

# Install config files
install(DIRECTORY
  Config
  DESTINATION share/${PROJECT_NAME}/
)

# Install message and service files
install(DIRECTORY
  msg
  srv
  DESTINATION share/${PROJECT_NAME}/
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  find_package(ament_cmake_pytest REQUIRED)
  
  # Linting
  ament_lint_auto_find_test_dependencies()
  
  # Python tests
  ament_add_pytest_test(test_work_area_manager tests/test_work_area_manager.py)
  ament_add_pytest_test(test_proximity_monitor tests/test_proximity_monitor.py)
endif()

ament_package()
