# WorkArea.msg
# Defines a robot's operational work area in 3D space

std_msgs/Header header
string robot_id
geometry_msgs/Point center
geometry_msgs/Vector3 dimensions  # width, height, depth in meters
float64 priority  # Task priority for conflict resolution (0=lowest, 4=highest)
