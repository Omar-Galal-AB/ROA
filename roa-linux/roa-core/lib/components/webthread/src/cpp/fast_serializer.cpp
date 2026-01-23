// fast_serializer.cpp
// ROA - Robot Operations & Automation
// High-performance data serialization for ROS2 ↔ UE5 communication

#include <cstring>
#include <vector>
#include <cstdint>
#include <iostream>

namespace ROA {
namespace Webthread {

/**
 * @brief FastSerializer
 * 
 * Provides high-performance binary serialization/deserialization
 * for data transfer between ROS2 and UE5 with minimal overhead.
 * 
 * This is a performance-critical component that should be optimized
 * for the target platform.
 */
class FastSerializer {
public:
    FastSerializer() : buffer_(), position_(0) {
        buffer_.reserve(4096);  // Pre-allocate 4KB
    }

    // Write methods
    void WriteInt32(int32_t value) {
        EnsureCapacity(sizeof(int32_t));
        std::memcpy(&buffer_[position_], &value, sizeof(int32_t));
        position_ += sizeof(int32_t);
    }

    void WriteFloat(float value) {
        EnsureCapacity(sizeof(float));
        std::memcpy(&buffer_[position_], &value, sizeof(float));
        position_ += sizeof(float);
    }

    void WriteDouble(double value) {
        EnsureCapacity(sizeof(double));
        std::memcpy(&buffer_[position_], &value, sizeof(double));
        position_ += sizeof(double);
    }

    void WriteString(const std::string& value) {
        uint32_t length = static_cast<uint32_t>(value.length());
        WriteInt32(length);
        EnsureCapacity(length);
        std::memcpy(&buffer_[position_], value.c_str(), length);
        position_ += length;
    }

    void WriteBytes(const uint8_t* data, size_t length) {
        EnsureCapacity(length);
        std::memcpy(&buffer_[position_], data, length);
        position_ += length;
    }

    // Read methods
    int32_t ReadInt32() {
        int32_t value;
        std::memcpy(&value, &buffer_[position_], sizeof(int32_t));
        position_ += sizeof(int32_t);
        return value;
    }

    float ReadFloat() {
        float value;
        std::memcpy(&value, &buffer_[position_], sizeof(float));
        position_ += sizeof(float);
        return value;
    }

    double ReadDouble() {
        double value;
        std::memcpy(&value, &buffer_[position_], sizeof(double));
        position_ += sizeof(double);
        return value;
    }

    std::string ReadString() {
        uint32_t length = ReadInt32();
        std::string value(reinterpret_cast<const char*>(&buffer_[position_]), length);
        position_ += length;
        return value;
    }

    void ReadBytes(uint8_t* data, size_t length) {
        std::memcpy(data, &buffer_[position_], length);
        position_ += length;
    }

    // Buffer management
    const uint8_t* GetBuffer() const {
        return buffer_.data();
    }

    size_t GetSize() const {
        return position_;
    }

    void Reset() {
        position_ = 0;
    }

    void Clear() {
        buffer_.clear();
        position_ = 0;
    }

    void SetBuffer(const uint8_t* data, size_t length) {
        buffer_.assign(data, data + length);
        position_ = 0;
    }

private:
    std::vector<uint8_t> buffer_;
    size_t position_;

    void EnsureCapacity(size_t additionalBytes) {
        size_t requiredSize = position_ + additionalBytes;
        if (requiredSize > buffer_.size()) {
            buffer_.resize(requiredSize * 2);  // Double the size for future growth
        }
    }
};

/**
 * @brief Serialize robot position data (optimized for frequent updates)
 */
class RobotPositionSerializer {
public:
    struct RobotPosition {
        int32_t robot_id;
        float x, y, z;              // Position
        float qw, qx, qy, qz;       // Orientation (quaternion)
        float vx, vy, vz;           // Linear velocity
        float wx, wy, wz;           // Angular velocity
        int64_t timestamp_us;       // Microseconds
    };

    static void Serialize(FastSerializer& serializer, const RobotPosition& pos) {
        serializer.WriteInt32(pos.robot_id);
        serializer.WriteFloat(pos.x);
        serializer.WriteFloat(pos.y);
        serializer.WriteFloat(pos.z);
        serializer.WriteFloat(pos.qw);
        serializer.WriteFloat(pos.qx);
        serializer.WriteFloat(pos.qy);
        serializer.WriteFloat(pos.qz);
        serializer.WriteFloat(pos.vx);
        serializer.WriteFloat(pos.vy);
        serializer.WriteFloat(pos.vz);
        serializer.WriteFloat(pos.wx);
        serializer.WriteFloat(pos.wy);
        serializer.WriteFloat(pos.wz);
        serializer.WriteInt32(static_cast<int32_t>(pos.timestamp_us >> 32));  // High 32 bits
        serializer.WriteInt32(static_cast<int32_t>(pos.timestamp_us & 0xFFFFFFFF));  // Low 32 bits
    }

    static RobotPosition Deserialize(FastSerializer& serializer) {
        RobotPosition pos;
        pos.robot_id = serializer.ReadInt32();
        pos.x = serializer.ReadFloat();
        pos.y = serializer.ReadFloat();
        pos.z = serializer.ReadFloat();
        pos.qw = serializer.ReadFloat();
        pos.qx = serializer.ReadFloat();
        pos.qy = serializer.ReadFloat();
        pos.qz = serializer.ReadFloat();
        pos.vx = serializer.ReadFloat();
        pos.vy = serializer.ReadFloat();
        pos.vz = serializer.ReadFloat();
        pos.wx = serializer.ReadFloat();
        pos.wy = serializer.ReadFloat();
        pos.wz = serializer.ReadFloat();
        int64_t high = serializer.ReadInt32();
        int64_t low = serializer.ReadInt32();
        pos.timestamp_us = (high << 32) | (low & 0xFFFFFFFF);
        return pos;
    }
};

// Example usage
void ExampleUsage() {
    FastSerializer serializer;

    // Serialize robot position
    RobotPositionSerializer::RobotPosition pos;
    pos.robot_id = 1;
    pos.x = 10.5f;
    pos.y = 20.3f;
    pos.z = 5.0f;
    pos.qw = 1.0f;
    pos.qx = 0.0f;
    pos.qy = 0.0f;
    pos.qz = 0.0f;
    pos.vx = 1.0f;
    pos.vy = 0.5f;
    pos.vz = 0.0f;
    pos.wx = 0.0f;
    pos.wy = 0.0f;
    pos.wz = 0.1f;
    pos.timestamp_us = 1234567890123456LL;

    RobotPositionSerializer::Serialize(serializer, pos);

    std::cout << "Serialized " << serializer.GetSize() << " bytes" << std::endl;

    // Deserialize
    serializer.Reset();  // Reset read position
    auto deserialized = RobotPositionSerializer::Deserialize(serializer);

    std::cout << "Robot ID: " << deserialized.robot_id << std::endl;
    std::cout << "Position: (" << deserialized.x << ", " 
              << deserialized.y << ", " << deserialized.z << ")" << std::endl;
}

} // namespace Webthread
} // namespace ROA

// Entry point for testing
int main() {
    ROA::Webthread::ExampleUsage();
    return 0;
}
