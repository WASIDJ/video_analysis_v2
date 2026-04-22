"""用于生成的 iOS 检测项的 Swift 策略模板。"""

from __future__ import annotations

from .registry import MetricItemRegistration


def render_strategy(registration: MetricItemRegistration) -> str:
    """根据注册信息渲染 Swift 策略源代码."""
    if registration.generator == "hip_abduction_mp33_v1":
        return _render_hip_abduction(registration)
    if registration.generator == "knee_symmetry_mp33_v1":
        return _render_knee_symmetry(registration)
    raise ValueError(f"Unsupported Swift generator: {registration.generator}")


def _render_hip_abduction(registration: MetricItemRegistration) -> str:
    return f"""import Foundation

// Auto-generated dry-run strategy for itemID {registration.item_id}.
// Matches the origin/dev iOS posture runtime:
// BaseStaticStrategy + evaluateStaticWithHold + Keypoints = [String: [Float]].
// Uses hold-duration completion: isCompleted only after sustained angle for holdDuration seconds.
public final class {registration.strategy}: BaseStaticStrategy {{

    public override init(itemID: String, itemType: DetectionItemType = .staticItem, parameters: [Float]) {{
        super.init(itemID: itemID, itemType: itemType, parameters: parameters)
    }}

    public override func process(keypoints: Keypoints, timestamp: Date) -> DetectionResult? {{
        guard
            let leftShoulder = keypoints["left_shoulder"],
            let rightShoulder = keypoints["right_shoulder"],
            let hip = keypoints["left_hip"] ?? keypoints["right_hip"],
            let knee = keypoints["left_knee"] ?? keypoints["right_knee"],
            leftShoulder.count >= 2,
            rightShoulder.count >= 2,
            hip.count >= 2,
            knee.count >= 2
        else {{
            return DetectionResult(itemID: itemID, score: 0.0, errorInfo: "missingBodyPart")
        }}

        let shoulderCenter = [
            (leftShoulder[0] + rightShoulder[0]) / 2.0,
            (leftShoulder[1] + rightShoulder[1]) / 2.0
        ]
        guard let angle = PA_calculateAngle(A: shoulderCenter, B: hip, C: knee) else {{
            return DetectionResult(itemID: itemID, score: 0.0, errorInfo: "invalidGeometry")
        }}

        let lower = parameters.count > 0 ? parameters[0] : 0.0
        let upper = parameters.count > 1 ? parameters[1] : 180.0
        let (score, errorInfo, isCompleted) = evaluateStaticWithHold(angle: angle, lower: lower, upper: upper, timestamp: timestamp)

        return DetectionResult(
            itemID: itemID,
            score: score,
            errorInfo: errorInfo,
            phase: "static",
            raiseCount: 0,
            isCompleted: isCompleted,
            errorMetrics: errorMetrics
        )
    }}
}}
"""


def _render_knee_symmetry(registration: MetricItemRegistration) -> str:
    return f"""import Foundation

// Auto-generated dry-run strategy for itemID {registration.item_id}.
// Matches the origin/dev iOS posture runtime:
// BaseStaticStrategy + evaluateStaticWithHold + Keypoints = [String: [Float]].
// Uses hold-duration completion: isCompleted only after sustained angle for holdDuration seconds.
// WARNING: knee_symmetry unit requires review — Python thresholds may be in degrees
// while this strategy computes abs(leftKnee[1] - rightKnee[1]) in normalized coordinates.
public final class {registration.strategy}: BaseStaticStrategy {{

    public override init(itemID: String, itemType: DetectionItemType = .staticItem, parameters: [Float]) {{
        super.init(itemID: itemID, itemType: itemType, parameters: parameters)
    }}

    public override func process(keypoints: Keypoints, timestamp: Date) -> DetectionResult? {{
        guard
            let leftKnee = keypoints["left_knee"],
            let rightKnee = keypoints["right_knee"],
            leftKnee.count >= 2,
            rightKnee.count >= 2
        else {{
            return DetectionResult(itemID: itemID, score: 0.0, errorInfo: "missingBodyPart")
        }}

        let verticalDifference = abs(leftKnee[1] - rightKnee[1])
        let lower = parameters.count > 0 ? parameters[0] : 0.0
        let upper = parameters.count > 1 ? parameters[1] : 180.0
        let (score, errorInfo, isCompleted) = evaluateStaticWithHold(angle: verticalDifference, lower: lower, upper: upper, timestamp: timestamp)

        return DetectionResult(
            itemID: itemID,
            score: score,
            errorInfo: errorInfo,
            phase: "static",
            raiseCount: 0,
            isCompleted: isCompleted,
            errorMetrics: errorMetrics
        )
    }}
}}
"""
