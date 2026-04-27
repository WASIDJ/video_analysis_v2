# 直腿抬高 iOS 侧 Swift 迁移代码（参考实现）

由于当前 AI 工作区权限限制，无法直接跨目录修改 `/Users/zzh/workspace/code/coaichingapp-IOS/Knieo`。请将以下代码参考实现复制到您的 iOS 工程对应的目录中。

## 1. 注册表与路由更新 (Registry & Factory)

需要在您的 `StrategyFactory` 或检测项注册表中添加对新 ID 的支持（指定其为 `mp33` 类型）：

```swift
// 伪代码：在您的注册表/工厂类中更新映射关系

// 1. 指定检测项依赖的关键点体系 (Profile)
let itemProfileMap: [Int: KeypointProfile] = [
    // ... 现有映射
    22: .mp33, // HipAbduction
    23: .mp33, // KneeSymmetry
    24: .mp33, // AnkleDorsiflexion (P1/P2 Counter)
    25: .mp33  // KneeFlexionCompensation (Dynamic Hold)
]

// 2. 注册策略实例构造器
func createStrategy(for itemID: Int, parameters: [Float]) -> DetectionItemStrategy? {
    switch itemID {
    // ... 现有工厂逻辑
    case 22:
        return HipAbductionMP33Strategy(parameters: parameters)
    case 23:
        return KneeSymmetryMP33Strategy(parameters: parameters)
    case 24:
        return AnkleDorsiflexionMP33Strategy(parameters: parameters)
    case 25:
        return KneeFlexionCompensationMP33Strategy(parameters: parameters)
    default:
        return nil
    }
}
```

## 2. itemID=24：踝背屈主计数策略 (AnkleDorsiflexionMP33Strategy)

该策略实现了 Python 测试脚本中的 **EMA 滤波**、**迟滞容差 (Hysteresis)** 和 **帧防抖 (Debounce)**，支持 8 槽位协议。

```swift
import Foundation

class AnkleDorsiflexionMP33Strategy: DetectionItemStrategy {
    let itemID = 24
    var parameters: [Float]
    
    // P1/P2 阈值
    private let enterP1: Float
    private let exitP1: Float
    private let enterP2: Float
    private let exitP2: Float
    
    // 质量评估阈值
    private let normalLower: Float
    private let excellentLower: Float
    private let excellentUpper: Float
    private let normalUpper: Float
    
    // 鲁棒性控制
    private let emaAlpha: Float = 0.4
    private var emaValue: Float? = nil
    private var prevEma: Float? = nil
    
    private let upMargin: Float
    private let downMargin: Float
    private let debounceFrames: Int = 2
    private let polarity: Polarity = .valleyToPeakToValley
    
    // 状态机
    private enum Phase { case p2Idle, p1Rise, p2Return }
    private var currentPhase: Phase = .p2Idle
    private var reachedPeak = false
    private var repCount = 0
    private var p1EntryCandidateFrames = 0
    private var p2EntryCandidateFrames = 0
    
    init(parameters: [Float]) {
        self.parameters = parameters
        // 解析 8 槽位
        self.enterP1 = parameters.count > 0 ? parameters[0] : 119.794
        self.exitP1 = parameters.count > 1 ? parameters[1] : 120.492
        self.enterP2 = parameters.count > 2 ? parameters[2] : 120.492
        self.exitP2 = parameters.count > 3 ? parameters[3] : 125.059
        
        self.normalLower = parameters.count > 4 ? parameters[4] : 119.95
        self.excellentLower = parameters.count > 5 ? parameters[5] : 124.81
        self.excellentUpper = parameters.count > 6 ? parameters[6] : 134.53
        self.normalUpper = parameters.count > 7 ? parameters[7] : 139.39
        
        self.upMargin = max(0.8, 0.03 * max(abs(self.exitP1 - self.enterP1), 1.0))
        self.downMargin = max(0.8, 0.03 * max(abs(self.enterP2 - self.exitP2), 1.0))
    }
    
    enum Polarity { case valleyToPeakToValley, peakToValleyToPeak }
    
    private func crossUp(val: Float, th: Float) -> Bool {
        return polarity == .valleyToPeakToValley ? val >= th : val <= th
    }
    
    private func crossDown(val: Float, th: Float) -> Bool {
        return polarity == .valleyToPeakToValley ? val <= th : val >= th
    }

    func process(keypoints: [String: Point3D], timestamp: TimeInterval) -> DetectionResult {
        // 1. 提取 MP33 关键点计算踝背屈角度
        guard let hip = keypoints["hip_joint"], // 伪代码：需替换为您实际的 mp33 枚举或字符串键
              let knee = keypoints["knee_joint"],
              let ankle = keypoints["ankle_joint"],
              let footIndex = keypoints["foot_index"] else {
            return DetectionResult(itemID: itemID, isCompleted: false, error: .missingBodyPart)
        }
        
        let rawAngle = GeometryUtils.calculateAngle(p1: knee, p2: ankle, p3: footIndex)
        
        // 2. EMA 滤波
        if emaValue == nil {
            emaValue = rawAngle
            prevEma = rawAngle
        } else {
            prevEma = emaValue
            emaValue = emaAlpha * rawAngle + (1 - emaAlpha) * emaValue!
        }
        
        let smoothValue = emaValue!
        
        // 3. P1/P2 状态机更新
        updateStateMachine(smoothValue: smoothValue)
        
        // 4. 质量评估逻辑（如在 Peak 阶段判断幅度是否达标）
        // ... (此处可使用 normalLower, excellentLower 等参数)
        
        return DetectionResult(itemID: itemID, repCount: repCount, phase: "\(currentPhase)")
    }
    
    private func updateStateMachine(smoothValue: Float) {
        let isValleyToPeak = polarity == .valleyToPeakToValley
        
        if currentPhase == .p2Idle {
            let marginTh = isValleyToPeak ? enterP1 + upMargin : enterP1 - upMargin
            if crossUp(val: smoothValue, th: marginTh) {
                p1EntryCandidateFrames += 1
                if p1EntryCandidateFrames >= debounceFrames {
                    currentPhase = .p1Rise
                    p1EntryCandidateFrames = 0
                }
            } else {
                p1EntryCandidateFrames = 0
            }
        }
        
        if currentPhase == .p1Rise && crossUp(val: smoothValue, th: exitP1) {
            reachedPeak = true
        }
        
        if currentPhase == .p1Rise && reachedPeak {
            let marginTh = isValleyToPeak ? enterP2 - downMargin : enterP2 + downMargin
            if crossDown(val: smoothValue, th: marginTh) {
                p2EntryCandidateFrames += 1
                if p2EntryCandidateFrames >= debounceFrames {
                    currentPhase = .p2Return
                    p2EntryCandidateFrames = 0
                }
            } else {
                p2EntryCandidateFrames = 0
            }
        }
        
        if currentPhase == .p2Return && crossUp(val: smoothValue, th: enterP2) {
            currentPhase = .p1Rise // 抗抖动：短暂回升继续留在 P1
        }
        
        if reachedPeak && currentPhase == .p2Return && crossDown(val: smoothValue, th: exitP2) {
            repCount += 1
            reachedPeak = false
            currentPhase = .p2Idle
        }
    }
}
```

## 3. itemID=25：动态膝盖代偿检测策略 (KneeFlexionCompensationMP33Strategy)

只在动作的 `Hold` 阶段生效，避免在 `Idle` 阶段产生误报。

```swift
class KneeFlexionCompensationMP33Strategy: DetectionItemStrategy {
    let itemID = 25
    var parameters: [Float]
    
    // ... 解析参数逻辑同上 [157.97, 162.16, 170.56, 174.75, ...]
    
    func process(keypoints: [String: Point3D], timestamp: TimeInterval, globalPhase: String) -> DetectionResult {
        // 如果当前不处于执行/保持阶段，则不报膝盖弯曲错误
        guard globalPhase == "hold" || globalPhase == "p1Rise" else {
            return DetectionResult(itemID: itemID, isCompleted: true)
        }
        
        // 计算膝盖角度并与参数判断
        // ...
        return DetectionResult(itemID: itemID, isCompleted: false, error: /* 根据阈值判断 */)
    }
}
```

## 4. 其它策略 (itemID 22, 23)
逻辑与 itemID 25 类似，核心在于：
1. 提取 mp33 特定的关键点（如髋关节外展计算）。
2. 在指定的有效相位（Hold）利用 8 槽位中的 `normal_range` 进行报错拦截。
