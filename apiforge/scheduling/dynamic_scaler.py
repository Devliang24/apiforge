"""
动态Worker扩缩容器

负责根据系统资源和任务队列状态动态调整Worker数量。
"""

import asyncio
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Callable, Any
from collections import deque

from apiforge.scheduling.models import (
    WorkerMetrics,
    SystemResourceMetrics,
    SchedulingDecision,
    ScalingAction
)
from apiforge.logger import logger


class DynamicWorkerScaler:
    """动态Worker扩缩容器"""
    
    def __init__(self, 
                 min_workers: int = 1,
                 max_workers: int = 10,
                 scale_up_threshold: float = 0.7,
                 scale_down_threshold: float = 0.3,
                 monitoring_interval: int = 30):
        """
        初始化动态扩缩容器
        
        Args:
            min_workers: 最小Worker数量
            max_workers: 最大Worker数量
            scale_up_threshold: 扩容阈值（队列使用率）
            scale_down_threshold: 缩容阈值（队列使用率）
            monitoring_interval: 监控间隔（秒）
        """
        self.min_workers = min_workers
        self.max_workers = max_workers
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.monitoring_interval = monitoring_interval
        
        # Worker管理
        self.workers: Dict[str, Any] = {}
        self.worker_metrics: Dict[str, WorkerMetrics] = {}
        
        # 资源监控历史
        self.resource_history = deque(maxlen=20)  # 保留最近20个数据点
        self.scaling_history = deque(maxlen=50)   # 保留最近50次扩缩容记录
        
        # 扩缩容控制
        self.last_scaling_time = None
        self.scaling_cooldown = 60  # 扩缩容冷却时间（秒）
        self.consecutive_scale_attempts = 0
        self.max_consecutive_scales = 3  # 连续扩缩容次数限制
        
        logger.info(f"DynamicWorkerScaler初始化: "
                   f"workers={min_workers}-{max_workers}, "
                   f"thresholds={scale_down_threshold:.1f}-{scale_up_threshold:.1f}")
    
    async def get_system_metrics(self) -> SystemResourceMetrics:
        """获取系统资源指标"""
        # CPU使用率（1秒平均值）
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # 内存使用情况
        memory = psutil.virtual_memory()
        memory_used_mb = memory.used / (1024 * 1024)
        memory_available_mb = memory.available / (1024 * 1024)
        
        # 获取活跃Worker数量
        active_workers = sum(1 for w in self.workers.values() 
                           if hasattr(w, 'is_running') and w.is_running)
        
        # 计算总队列大小（需要从Worker获取）
        total_queue_size = sum(
            self.worker_metrics.get(worker_id, WorkerMetrics(
                worker_id=worker_id,
                status="unknown"
            )).queue_size
            for worker_id in self.workers
        )
        
        return SystemResourceMetrics(
            total_cpu_usage_percent=cpu_percent,
            total_memory_usage_mb=memory_used_mb,
            available_memory_mb=memory_available_mb,
            active_worker_count=active_workers,
            total_queue_size=total_queue_size
        )
    
    def update_worker_metrics(self, worker_id: str, metrics: WorkerMetrics) -> None:
        """
        更新Worker指标
        
        Args:
            worker_id: Worker ID
            metrics: Worker指标
        """
        self.worker_metrics[worker_id] = metrics
    
    def get_worker_metrics(self) -> List[WorkerMetrics]:
        """获取所有Worker的指标"""
        return list(self.worker_metrics.values())
    
    async def evaluate_scaling_need(self) -> SchedulingDecision:
        """
        评估是否需要扩缩容
        
        Returns:
            调度决策
        """
        # 获取系统指标
        system_metrics = await self.get_system_metrics()
        
        # 记录资源历史
        self.resource_history.append({
            "timestamp": datetime.now(),
            "metrics": system_metrics
        })
        
        # 检查是否在冷却期内
        if self._in_cooldown_period():
            return self._create_decision(
                ScalingAction.MAINTAIN,
                system_metrics.active_worker_count,
                "In cooldown period"
            )
        
        # 计算队列压力
        queue_pressure = self._calculate_queue_pressure()
        
        # 检查资源限制
        resource_constraints = self._check_resource_constraints(system_metrics)
        
        # 做出扩缩容决策
        if queue_pressure > self.scale_up_threshold and not resource_constraints["at_limit"]:
            # 需要扩容
            if system_metrics.active_worker_count < self.max_workers:
                return self._create_scale_up_decision(
                    system_metrics.active_worker_count,
                    queue_pressure,
                    resource_constraints
                )
        
        elif queue_pressure < self.scale_down_threshold:
            # 可以缩容
            if system_metrics.active_worker_count > self.min_workers:
                return self._create_scale_down_decision(
                    system_metrics.active_worker_count,
                    queue_pressure
                )
        
        # 保持现状
        return self._create_decision(
            ScalingAction.MAINTAIN,
            system_metrics.active_worker_count,
            f"Queue pressure {queue_pressure:.2f} within thresholds"
        )
    
    def _in_cooldown_period(self) -> bool:
        """检查是否在冷却期内"""
        if not self.last_scaling_time:
            return False
        
        elapsed = (datetime.now() - self.last_scaling_time).total_seconds()
        return elapsed < self.scaling_cooldown
    
    def _calculate_queue_pressure(self) -> float:
        """
        计算队列压力（0-1）
        
        Returns:
            队列压力值
        """
        if not self.worker_metrics:
            return 0.0
        
        total_pending = sum(m.pending_tasks for m in self.worker_metrics.values())
        total_capacity = len(self.worker_metrics) * 100  # 假设每个Worker容量为100
        
        if total_capacity == 0:
            return 0.0
        
        # 考虑完成速率
        completion_rate = self._calculate_completion_rate()
        if completion_rate > 0:
            # 预估清空队列所需时间（分钟）
            time_to_clear = total_pending / (completion_rate * 60)
            # 如果预计超过5分钟才能清空，增加压力
            time_pressure = min(time_to_clear / 5.0, 1.0)
        else:
            time_pressure = 1.0 if total_pending > 0 else 0.0
        
        # 综合队列使用率和时间压力
        queue_usage = total_pending / total_capacity
        return (queue_usage + time_pressure) / 2.0
    
    def _calculate_completion_rate(self) -> float:
        """计算任务完成速率（任务/秒）"""
        if len(self.resource_history) < 2:
            return 0.0
        
        # 比较最近两个时间点的完成任务数
        recent = self.resource_history[-1]
        previous = self.resource_history[-2]
        
        time_diff = (recent["timestamp"] - previous["timestamp"]).total_seconds()
        if time_diff == 0:
            return 0.0
        
        # 计算所有Worker的完成任务数变化
        recent_completed = sum(m.tasks_completed for m in self.worker_metrics.values())
        # 这里简化处理，实际应该比较两个时间点的值
        return recent_completed / max(time_diff, 1)
    
    def _check_resource_constraints(self, metrics: SystemResourceMetrics) -> Dict[str, any]:
        """检查资源限制"""
        constraints = {
            "at_limit": False,
            "cpu_limited": False,
            "memory_limited": False,
            "reasons": []
        }
        
        # 检查CPU限制
        if metrics.total_cpu_usage_percent > metrics.cpu_threshold:
            constraints["cpu_limited"] = True
            constraints["reasons"].append(f"CPU usage {metrics.total_cpu_usage_percent:.1f}% > {metrics.cpu_threshold}%")
        
        # 检查内存限制
        if metrics.available_memory_mb < metrics.memory_threshold_mb:
            constraints["memory_limited"] = True
            constraints["reasons"].append(f"Available memory {metrics.available_memory_mb:.0f}MB < {metrics.memory_threshold_mb}MB")
        
        constraints["at_limit"] = constraints["cpu_limited"] or constraints["memory_limited"]
        
        return constraints
    
    def _create_scale_up_decision(self, current_workers: int, 
                                 queue_pressure: float,
                                 resource_constraints: Dict) -> SchedulingDecision:
        """创建扩容决策"""
        # 根据队列压力决定扩容数量
        if queue_pressure > 0.9:
            scale_amount = min(2, self.max_workers - current_workers)
        else:
            scale_amount = 1
        
        target_workers = current_workers + scale_amount
        
        # 评估影响
        estimated_impact = {
            "expected_queue_reduction": f"{scale_amount * 20}%",
            "additional_resource_usage": {
                "cpu": f"+{scale_amount * 10}%",
                "memory": f"+{scale_amount * 200}MB"
            },
            "queue_pressure": queue_pressure
        }
        
        return SchedulingDecision(
            action=ScalingAction.SCALE_UP,
            current_workers=current_workers,
            target_workers=target_workers,
            reason=f"High queue pressure ({queue_pressure:.2f})",
            confidence=0.8 if not resource_constraints["at_limit"] else 0.6,
            estimated_impact=estimated_impact,
            risk_level="low" if scale_amount == 1 else "medium",
            potential_issues=resource_constraints.get("reasons", [])
        )
    
    def _create_scale_down_decision(self, current_workers: int,
                                   queue_pressure: float) -> SchedulingDecision:
        """创建缩容决策"""
        # 保守缩容，一次只减少1个Worker
        target_workers = current_workers - 1
        
        estimated_impact = {
            "expected_queue_increase": "minimal" if queue_pressure < 0.1 else f"+{20}%",
            "resource_savings": {
                "cpu": "-10%",
                "memory": "-200MB"
            },
            "queue_pressure": queue_pressure
        }
        
        return SchedulingDecision(
            action=ScalingAction.SCALE_DOWN,
            current_workers=current_workers,
            target_workers=target_workers,
            reason=f"Low queue pressure ({queue_pressure:.2f})",
            confidence=0.9 if queue_pressure < 0.1 else 0.7,
            estimated_impact=estimated_impact,
            risk_level="low"
        )
    
    def _create_decision(self, action: ScalingAction, 
                        current_workers: int,
                        reason: str) -> SchedulingDecision:
        """创建维持现状的决策"""
        return SchedulingDecision(
            action=action,
            current_workers=current_workers,
            target_workers=current_workers,
            reason=reason,
            confidence=0.95,
            estimated_impact={"status": "stable"}
        )
    
    async def execute_scaling(self, decision: SchedulingDecision,
                            worker_factory: Callable) -> bool:
        """
        执行扩缩容决策
        
        Args:
            decision: 调度决策
            worker_factory: Worker工厂函数
            
        Returns:
            是否成功执行
        """
        if decision.action == ScalingAction.MAINTAIN:
            return True
        
        try:
            if decision.action == ScalingAction.SCALE_UP:
                success = await self._scale_up(
                    decision.target_workers - decision.current_workers,
                    worker_factory
                )
            else:  # SCALE_DOWN
                success = await self._scale_down(
                    decision.current_workers - decision.target_workers
                )
            
            if success:
                # 记录扩缩容历史
                self.scaling_history.append({
                    "timestamp": datetime.now(),
                    "action": decision.action,
                    "from_workers": decision.current_workers,
                    "to_workers": decision.target_workers,
                    "reason": decision.reason
                })
                
                # 更新最后扩缩容时间
                self.last_scaling_time = datetime.now()
                
                # 更新连续扩缩容计数
                if len(self.scaling_history) > 1:
                    last_action = self.scaling_history[-2]["action"]
                    if last_action == decision.action:
                        self.consecutive_scale_attempts += 1
                    else:
                        self.consecutive_scale_attempts = 1
                else:
                    self.consecutive_scale_attempts = 1
                
                logger.info(f"扩缩容成功: {decision.action.value} "
                          f"从 {decision.current_workers} 到 {decision.target_workers}")
            
            return success
            
        except Exception as e:
            logger.error(f"扩缩容执行失败: {str(e)}")
            return False
    
    async def _scale_up(self, count: int, worker_factory: Callable) -> bool:
        """
        扩容Worker
        
        Args:
            count: 扩容数量
            worker_factory: Worker工厂函数
            
        Returns:
            是否成功
        """
        try:
            for i in range(count):
                worker_id = f"worker_{len(self.workers) + 1}"
                worker = await worker_factory(worker_id)
                
                if worker:
                    self.workers[worker_id] = worker
                    self.worker_metrics[worker_id] = WorkerMetrics(
                        worker_id=worker_id,
                        status="starting"
                    )
                    logger.info(f"创建新Worker: {worker_id}")
                else:
                    logger.error(f"创建Worker失败: {worker_id}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"扩容失败: {str(e)}")
            return False
    
    async def _scale_down(self, count: int) -> bool:
        """
        缩容Worker
        
        Args:
            count: 缩容数量
            
        Returns:
            是否成功
        """
        try:
            # 选择要停止的Worker（优先选择空闲的）
            workers_to_stop = self._select_workers_to_stop(count)
            
            for worker_id in workers_to_stop:
                worker = self.workers.get(worker_id)
                if worker and hasattr(worker, 'stop'):
                    await worker.stop()
                    del self.workers[worker_id]
                    del self.worker_metrics[worker_id]
                    logger.info(f"停止Worker: {worker_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"缩容失败: {str(e)}")
            return False
    
    def _select_workers_to_stop(self, count: int) -> List[str]:
        """选择要停止的Worker"""
        # 按照任务数量排序，优先停止任务少的Worker
        sorted_workers = sorted(
            self.worker_metrics.items(),
            key=lambda x: x[1].pending_tasks + x[1].tasks_completed
        )
        
        return [worker_id for worker_id, _ in sorted_workers[:count]]
    
    def get_scaling_summary(self) -> Dict[str, any]:
        """获取扩缩容摘要"""
        return {
            "current_workers": len(self.workers),
            "active_workers": sum(1 for m in self.worker_metrics.values() 
                                if m.status == "running"),
            "worker_range": f"{self.min_workers}-{self.max_workers}",
            "thresholds": {
                "scale_up": self.scale_up_threshold,
                "scale_down": self.scale_down_threshold
            },
            "recent_scaling_events": len(self.scaling_history),
            "last_scaling": self.scaling_history[-1] if self.scaling_history else None,
            "resource_usage": self.resource_history[-1]["metrics"].__dict__ 
                            if self.resource_history else None
        }
    
    async def cleanup(self) -> None:
        """清理所有Worker"""
        for worker_id, worker in list(self.workers.items()):
            try:
                if hasattr(worker, 'stop'):
                    await worker.stop()
                del self.workers[worker_id]
                del self.worker_metrics[worker_id]
            except Exception as e:
                logger.error(f"清理Worker {worker_id} 失败: {str(e)}")