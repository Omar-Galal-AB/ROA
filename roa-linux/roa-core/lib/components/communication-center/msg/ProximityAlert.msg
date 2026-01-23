# ProximityAlert.msg
# Real-time collision warning between robots

std_msgs/Header header
string source_robot_id
string target_robot_id
float64 current_distance  # meters
float64 approach_velocity  # m/s (negative = moving away)
string severity  # "warning", "caution", "critical"
