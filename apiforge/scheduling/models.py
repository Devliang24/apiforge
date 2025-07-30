"""
智能调度系统数据模型

定义调度系统中使用的核心数据结构和枚举类型。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class ExecutionMode(Enum):
    """执行模式枚举"""
    AUTO = "auto"           # 智能渐进式 (默认推荐)
    FAST = "fast"          # 极速模式
    SMART = "smart"        # 纯动态调度
    AI_ANALYSIS = "ai-analysis"  # AI深度分析


class APIComplexityLevel(Enum):
    """API复杂度等级"""
    SIMPLE = "simple"       # 简单 (1-20个端点，基础CRUD)
    MEDIUM = "medium"       # 中等 (21-50个端点，有业务逻辑)
    COMPLEX = "complex"     # 复杂 (51-100个端点，复杂业务流)
    VERY_COMPLEX = "very_complex"  # 极复杂 (100+端点，复杂依赖)


class ScalingAction(Enum):
    """扩缩容动作"""
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    MAINTAIN = "maintain"


@dataclass
class ComplexityMetrics:
    """API复杂度评估指标"""
    endpoint_count: int
    method_distribution: Dict[str, int]  # {"GET": 10, "POST": 5, ...}
    parameter_complexity_score: float    # 0.0-10.0
    auth_complexity_score: float         # 0.0-10.0
    schema_depth_avg: float             # 平均schema嵌套深度
    business_dependency_score: float     # 业务依赖复杂度 0.0-10.0
    overall_complexity: APIComplexityLevel
    
    # 计算得出的推荐值
    estimated_test_cases_per_endpoint: int = 6
    estimated_total_processing_time_minutes: float = 0.0


@dataclass
class APIPattern:
    """API模式识别结果"""
    pattern_name: str                    # 模式名称，如 "RESTful CRUD", "GraphQL", "RPC"
    confidence_score: float              # 0.0-1.0 识别置信度
    complexity_metrics: ComplexityMetrics
    
    # 推荐配置
    safe_start_workers: int = 2          # 安全启动worker数
    recommended_max_workers: int = 4     # 推荐最大worker数
    optimal_workers: int = 3             # 最优worker数
    
    # 历史数据支持
    similar_apis_count: int = 0          # 相似API数量
    success_rate_with_recommended: float = 0.0  # 推荐配置成功率
    
    # 额外元数据
    detected_features: List[str] = field(default_factory=list)  # ["pagination", "filtering", "auth"]
    risk_factors: List[str] = field(default_factory=list)       # ["high_complexity", "rate_limited"]


@dataclass
class WorkerMetrics:
    """Worker性能指标"""
    worker_id: str
    status: str                         # "running", "idle", "error"
    current_task_id: Optional[str] = None
    
    # 性能指标
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_task_duration_seconds: float = 0.0
    current_task_start_time: Optional[datetime] = None
    
    # 资源使用
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    
    # 队列状态
    queue_size: int = 0
    pending_tasks: int = 0


@dataclass
class SystemResourceMetrics:
    """系统资源指标"""
    total_cpu_usage_percent: float
    total_memory_usage_mb: float
    available_memory_mb: float
    active_worker_count: int
    total_queue_size: int
    
    # 性能阈值
    cpu_threshold: float = 80.0
    memory_threshold_mb: float = 1000.0


@dataclass
class SchedulingDecision:
    """调度决策结果"""
    action: ScalingAction
    current_workers: int
    target_workers: int
    reason: str
    confidence: float                    # 0.0-1.0 决策置信度
    estimated_impact: Dict[str, Any]     # 预期影响
    
    # 决策时间戳
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 风险评估
    risk_level: str = "low"             # "low", "medium", "high"
    potential_issues: List[str] = field(default_factory=list)


@dataclass
class ProgressivePhase:
    """渐进式调度阶段"""
    phase_name: str                     # "exploration", "optimization", "stabilization"
    min_duration_seconds: int           # 最短持续时间
    target_workers: int
    max_duration_seconds: Optional[int] = None  # 最长持续时间
    
    # 阶段条件
    entry_conditions: List[str] = field(default_factory=list)
    exit_conditions: List[str] = field(default_factory=list)
    
    # 监控指标
    success_criteria: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionStrategy:
    """执行策略配置"""
    mode: ExecutionMode
    initial_workers: int
    max_workers: int
    min_workers: int = 1
    
    # 调度参数
    scale_up_threshold: float = 0.7      # 队列积压比例阈值
    scale_down_threshold: float = 0.3    # 空闲比例阈值
    monitoring_interval_seconds: int = 30
    
    # 安全设置
    enable_auto_scaling: bool = True
    enable_progressive_phases: bool = True
    max_scale_events_per_hour: int = 10
    
    # 特殊配置
    custom_phases: List[ProgressivePhase] = field(default_factory=list)
    override_settings: Dict[str, Any] = field(default_factory=dict)


@dataclass  
class SchedulingReport:
    """调度报告"""
    session_id: str
    execution_mode: ExecutionMode
    start_time: datetime
    end_time: Optional[datetime] = None
    
    # 执行统计
    total_endpoints: int = 0
    completed_endpoints: int = 0
    failed_endpoints: int = 0
    total_test_cases_generated: int = 0
    
    # Worker统计
    peak_workers: int = 0
    worker_utilization_avg: float = 0.0
    total_scaling_events: int = 0
    
    # 性能指标
    avg_endpoint_processing_time: float = 0.0
    total_execution_time_seconds: float = 0.0
    throughput_endpoints_per_minute: float = 0.0
    
    # 智能调度效果
    scheduling_decisions: List[SchedulingDecision] = field(default_factory=list)
    pattern_detection_accuracy: float = 0.0
    recommended_vs_actual_variance: float = 0.0
    
    # 用户反馈
    user_satisfaction_score: Optional[float] = None
    user_feedback: Optional[str] = None