# TaskCoordination.msg
# Multi-robot task coordination status

std_msgs/Header header
string robot_id
string task_id
string task_type
string[] required_resources
uint8 priority
string status  # "requested", "approved", "executing", "completed", "failed"
