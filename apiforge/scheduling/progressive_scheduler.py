"""
渐进式调度器

管理智能调度的不同阶段（探索、优化、稳定），根据实时反馈动态调整策略。
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

from apiforge.scheduling.models import (
    ProgressivePhase,
    WorkerMetrics,
    SchedulingDecision,
    ScalingAction,
    APIPattern,
    ExecutionMode
)
from apiforge.logger import logger


class PhaseStatus(Enum):
    """阶段状态"""
    PENDING = "pending"      # 等待开始
    ACTIVE = "active"        # 正在执行
    COMPLETED = "completed"  # 已完成
    SKIPPED = "skipped"     # 已跳过


class ProgressiveScheduler:
    """渐进式调度器"""
    
    def __init__(self, execution_mode: ExecutionMode, api_pattern: APIPattern):
        """
        初始化渐进式调度器
        
        Args:
            execution_mode: 执行模式
            api_pattern: API模式分析结果
        """
        self.execution_mode = execution_mode
        self.api_pattern = api_pattern
        
        # 初始化阶段配置
        self.phases = self._initialize_phases()
        self.current_phase_index = 0
        self.phase_start_time = None
        self.phase_metrics: Dict[str, Dict[str, Any]] = {}
        
        # 性能跟踪
        self.performance_history: List[Dict[str, Any]] = []
        self.stability_window = 5  # 稳定性评估窗口（分钟）
        
        logger.info(f"ProgressiveScheduler初始化: 模式={execution_mode.value}, "
                   f"API类型={api_pattern.pattern_name}")
    
    def _initialize_phases(self) -> List[ProgressivePhase]:
        """根据执行模式初始化阶段配置"""
        if self.execution_mode == ExecutionMode.FAST:
            # 极速模式：直接进入最大并发
            return [
                ProgressivePhase(
                    phase_name="fast_execution",
                    min_duration_seconds=0,
                    target_workers=self.api_pattern.recommended_max_workers,
                    entry_conditions=["immediate"],
                    exit_conditions=["all_tasks_completed"],
                    success_criteria={"completion_rate": 0.95}
                )
            ]
        
        elif self.execution_mode == ExecutionMode.SMART:
            # 纯动态调度：没有固定阶段
            return [
                ProgressivePhase(
                    phase_name="dynamic",
                    min_duration_seconds=0,
                    target_workers=self.api_pattern.optimal_workers,
                    entry_conditions=["immediate"],
                    exit_conditions=["all_tasks_completed"],
                    success_criteria={"adaptive": True}
                )
            ]
        
        # AUTO模式：标准三阶段
        exploration_duration = 180  # 3分钟
        optimization_duration = 300  # 5分钟
        
        return [
            # 探索阶段
            ProgressivePhase(
                phase_name="exploration",
                min_duration_seconds=exploration_duration,
                max_duration_seconds=exploration_duration * 2,
                target_workers=self.api_pattern.safe_start_workers,
                entry_conditions=["start"],
                exit_conditions=[
                    "min_duration_reached",
                    "stable_performance"
                ],
                success_criteria={
                    "error_rate": 0.1,  # 错误率低于10%
                    "avg_response_time": 5.0  # 平均响应时间低于5秒
                }
            ),
            
            # 优化阶段
            ProgressivePhase(
                phase_name="optimization",
                min_duration_seconds=optimization_duration,
                max_duration_seconds=optimization_duration * 2,
                target_workers=self.api_pattern.optimal_workers,
                entry_conditions=[
                    "exploration_completed",
                    "system_stable"
                ],
                exit_conditions=[
                    "optimal_performance_reached",
                    "diminishing_returns"
                ],
                success_criteria={
                    "throughput_improvement": 0.2,  # 吞吐量提升20%
                    "error_rate": 0.05  # 错误率低于5%
                }
            ),
            
            # 稳定阶段
            ProgressivePhase(
                phase_name="stabilization",
                min_duration_seconds=0,
                target_workers=self._calculate_stable_workers(),
                entry_conditions=[
                    "optimization_completed"
                ],
                exit_conditions=[
                    "all_tasks_completed"
                ],
                success_criteria={
                    "maintain_performance": True,
                    "error_rate": 0.05
                }
            )
        ]
    
    def _calculate_stable_workers(self) -> int:
        """计算稳定阶段的worker数量"""
        # 在优化和推荐最大值之间取中间值
        optimal = self.api_pattern.optimal_workers
        max_workers = self.api_pattern.recommended_max_workers
        return optimal + (max_workers - optimal) // 2
    
    def get_current_phase(self) -> Optional[ProgressivePhase]:
        """获取当前执行阶段"""
        if 0 <= self.current_phase_index < len(self.phases):
            return self.phases[self.current_phase_index]
        return None
    
    def should_transition(self, metrics: List[WorkerMetrics]) -> bool:
        """
        判断是否应该转换到下一阶段
        
        Args:
            metrics: Worker性能指标列表
            
        Returns:
            是否应该转换阶段
        """
        current_phase = self.get_current_phase()
        if not current_phase:
            return False
        
        # 检查最小持续时间
        if self.phase_start_time:
            elapsed = (datetime.now() - self.phase_start_time).total_seconds()
            if elapsed < current_phase.min_duration_seconds:
                return False
            
            # 检查最大持续时间
            if (current_phase.max_duration_seconds and 
                elapsed > current_phase.max_duration_seconds):
                logger.info(f"阶段 {current_phase.phase_name} 达到最大持续时间")
                return True
        
        # 检查退出条件
        for condition in current_phase.exit_conditions:
            if self._check_exit_condition(condition, metrics):
                logger.info(f"阶段 {current_phase.phase_name} 满足退出条件: {condition}")
                return True
        
        return False
    
    def _check_exit_condition(self, condition: str, 
                             metrics: List[WorkerMetrics]) -> bool:
        """检查特定的退出条件"""
        if condition == "min_duration_reached":
            if self.phase_start_time:
                elapsed = (datetime.now() - self.phase_start_time).total_seconds()
                current_phase = self.get_current_phase()
                return elapsed >= current_phase.min_duration_seconds
        
        elif condition == "stable_performance":
            return self._is_performance_stable(metrics)
        
        elif condition == "optimal_performance_reached":
            return self._is_performance_optimal(metrics)
        
        elif condition == "diminishing_returns":
            return self._has_diminishing_returns()
        
        elif condition == "all_tasks_completed":
            # 检查是否所有任务都已完成
            total_pending = sum(m.pending_tasks for m in metrics)
            return total_pending == 0
        
        return False
    
    def _is_performance_stable(self, metrics: List[WorkerMetrics]) -> bool:
        """判断性能是否稳定"""
        if len(self.performance_history) < 3:
            return False
        
        # 检查最近3个数据点的方差
        recent_throughputs = [p["throughput"] for p in self.performance_history[-3:]]
        if not recent_throughputs:
            return False
        
        avg = sum(recent_throughputs) / len(recent_throughputs)
        variance = sum((x - avg) ** 2 for x in recent_throughputs) / len(recent_throughputs)
        
        # 方差小于平均值的10%认为稳定
        return variance < (avg * 0.1) ** 2
    
    def _is_performance_optimal(self, metrics: List[WorkerMetrics]) -> bool:
        """判断是否达到最优性能"""
        current_phase = self.get_current_phase()
        if not current_phase or "throughput_improvement" not in current_phase.success_criteria:
            return False
        
        if len(self.performance_history) < 2:
            return False
        
        # 比较当前和初始性能
        initial_throughput = self.performance_history[0].get("throughput", 0)
        current_throughput = self.performance_history[-1].get("throughput", 0)
        
        if initial_throughput == 0:
            return False
        
        improvement = (current_throughput - initial_throughput) / initial_throughput
        target_improvement = current_phase.success_criteria["throughput_improvement"]
        
        return improvement >= target_improvement
    
    def _has_diminishing_returns(self) -> bool:
        """判断是否出现收益递减"""
        if len(self.performance_history) < 5:
            return False
        
        # 检查最近5个数据点的改善趋势
        recent = self.performance_history[-5:]
        improvements = []
        
        for i in range(1, len(recent)):
            prev_throughput = recent[i-1].get("throughput", 0)
            curr_throughput = recent[i].get("throughput", 0)
            
            if prev_throughput > 0:
                improvement = (curr_throughput - prev_throughput) / prev_throughput
                improvements.append(improvement)
        
        if not improvements:
            return False
        
        # 如果平均改善率低于2%，认为收益递减
        avg_improvement = sum(improvements) / len(improvements)
        return avg_improvement < 0.02
    
    def transition_to_next_phase(self) -> bool:
        """
        转换到下一阶段
        
        Returns:
            是否成功转换
        """
        if self.current_phase_index >= len(self.phases) - 1:
            return False
        
        current_phase = self.get_current_phase()
        if current_phase:
            # 记录当前阶段的最终指标
            self.phase_metrics[current_phase.phase_name] = {
                "end_time": datetime.now(),
                "duration": (datetime.now() - self.phase_start_time).total_seconds() 
                           if self.phase_start_time else 0,
                "final_metrics": self.performance_history[-1] if self.performance_history else {}
            }
        
        # 切换到下一阶段
        self.current_phase_index += 1
        self.phase_start_time = datetime.now()
        
        next_phase = self.get_current_phase()
        if next_phase:
            logger.info(f"转换到阶段: {next_phase.phase_name}, "
                       f"目标Worker数: {next_phase.target_workers}")
            return True
        
        return False
    
    def update_performance_metrics(self, metrics: List[WorkerMetrics]) -> None:
        """
        更新性能指标
        
        Args:
            metrics: Worker性能指标列表
        """
        if not metrics:
            return
        
        # 计算聚合指标
        total_completed = sum(m.tasks_completed for m in metrics)
        total_failed = sum(m.tasks_failed for m in metrics)
        total_tasks = total_completed + total_failed
        
        avg_duration = sum(m.avg_task_duration_seconds * m.tasks_completed 
                         for m in metrics) / max(total_completed, 1)
        
        # 计算吞吐量（每分钟完成的任务数）
        if self.phase_start_time:
            elapsed_minutes = (datetime.now() - self.phase_start_time).total_seconds() / 60
            throughput = total_completed / max(elapsed_minutes, 1)
        else:
            throughput = 0
        
        # 记录性能数据
        performance_data = {
            "timestamp": datetime.now(),
            "phase": self.get_current_phase().phase_name if self.get_current_phase() else "unknown",
            "total_completed": total_completed,
            "total_failed": total_failed,
            "error_rate": total_failed / max(total_tasks, 1),
            "avg_duration": avg_duration,
            "throughput": throughput,
            "active_workers": sum(1 for m in metrics if m.status == "running")
        }
        
        self.performance_history.append(performance_data)
        
        # 限制历史记录大小
        if len(self.performance_history) > 100:
            self.performance_history = self.performance_history[-100:]
    
    def get_scaling_recommendation(self) -> SchedulingDecision:
        """
        获取扩缩容建议
        
        Returns:
            调度决策
        """
        current_phase = self.get_current_phase()
        if not current_phase:
            return SchedulingDecision(
                action=ScalingAction.MAINTAIN,
                current_workers=0,
                target_workers=0,
                reason="No active phase",
                confidence=0.0,
                estimated_impact={}
            )
        
        # 获取当前性能
        if self.performance_history:
            current_perf = self.performance_history[-1]
            current_workers = current_perf.get("active_workers", 0)
        else:
            current_workers = 0
        
        target_workers = current_phase.target_workers
        
        # 确定扩缩容动作
        if current_workers < target_workers:
            action = ScalingAction.SCALE_UP
            reason = f"阶段 {current_phase.phase_name} 需要 {target_workers} 个worker"
        elif current_workers > target_workers:
            action = ScalingAction.SCALE_DOWN
            reason = f"阶段 {current_phase.phase_name} 只需要 {target_workers} 个worker"
        else:
            action = ScalingAction.MAINTAIN
            reason = f"当前worker数量符合阶段 {current_phase.phase_name} 的要求"
        
        # 评估影响
        estimated_impact = self._estimate_scaling_impact(
            current_workers, target_workers, current_phase
        )
        
        return SchedulingDecision(
            action=action,
            current_workers=current_workers,
            target_workers=target_workers,
            reason=reason,
            confidence=0.85,  # 基于阶段的决策通常有较高置信度
            estimated_impact=estimated_impact
        )
    
    def _estimate_scaling_impact(self, current_workers: int, 
                               target_workers: int,
                               phase: ProgressivePhase) -> Dict[str, Any]:
        """估算扩缩容的影响"""
        if current_workers == 0:
            throughput_change = 0
        else:
            # 简化模型：假设吞吐量与worker数量成次线性关系
            scaling_factor = 0.8  # 并发效率因子
            throughput_change = ((target_workers ** scaling_factor) - 
                               (current_workers ** scaling_factor)) / (current_workers ** scaling_factor)
        
        return {
            "expected_throughput_change": f"{throughput_change*100:.1f}%",
            "phase_target": phase.phase_name,
            "risk_level": "low" if abs(target_workers - current_workers) <= 2 else "medium"
        }
    
    def get_phase_summary(self) -> Dict[str, Any]:
        """获取阶段执行摘要"""
        current_phase = self.get_current_phase()
        
        return {
            "current_phase": current_phase.phase_name if current_phase else None,
            "phase_progress": self._calculate_phase_progress(),
            "phases_completed": self.current_phase_index,
            "total_phases": len(self.phases),
            "phase_metrics": self.phase_metrics,
            "current_performance": self.performance_history[-1] if self.performance_history else None
        }
    
    def _calculate_phase_progress(self) -> float:
        """计算当前阶段的进度（0-1）"""
        current_phase = self.get_current_phase()
        if not current_phase or not self.phase_start_time:
            return 0.0
        
        elapsed = (datetime.now() - self.phase_start_time).total_seconds()
        
        if current_phase.min_duration_seconds > 0:
            progress = elapsed / current_phase.min_duration_seconds
            return min(progress, 1.0)
        
        return 0.5  # 没有明确持续时间的阶段返回50%进度