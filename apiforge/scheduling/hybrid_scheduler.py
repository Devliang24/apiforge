"""
混合智能调度器

整合API模式识别、渐进式调度和动态扩缩容，提供统一的智能调度接口。
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Tuple
from enum import Enum

from apiforge.scheduling.models import (
    ExecutionMode,
    APIPattern,
    WorkerMetrics,
    SchedulingDecision,
    ScalingAction,
    SchedulingReport,
    ExecutionStrategy
)
from apiforge.scheduling.api_pattern_matcher import APIPatternMatcher
from apiforge.scheduling.progressive_scheduler import ProgressiveScheduler
from apiforge.scheduling.dynamic_scaler import DynamicWorkerScaler
from apiforge.parser.spec_parser import EndpointInfo
from apiforge.logger import logger


class SchedulerState(Enum):
    """调度器状态"""
    INITIALIZING = "initializing"
    ANALYZING = "analyzing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"


class HybridIntelligentScheduler:
    """混合智能调度器"""
    
    def __init__(self, 
                 execution_mode: ExecutionMode = ExecutionMode.AUTO,
                 execution_strategy: Optional[ExecutionStrategy] = None):
        """
        初始化混合智能调度器
        
        Args:
            execution_mode: 执行模式
            execution_strategy: 执行策略（可选，提供则覆盖默认策略）
        """
        self.execution_mode = execution_mode
        self.state = SchedulerState.INITIALIZING
        
        # 核心组件
        self.pattern_matcher = APIPatternMatcher()
        self.progressive_scheduler = None  # 在分析API后初始化
        self.dynamic_scaler = None  # 根据策略初始化
        
        # API分析结果
        self.api_pattern: Optional[APIPattern] = None
        self.endpoints: List[EndpointInfo] = []
        
        # 执行策略
        self.execution_strategy = execution_strategy or self._create_default_strategy()
        
        # 调度状态
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.start_time = None
        self.scheduling_task = None
        self.is_running = False
        
        # 监控数据
        self.scheduling_decisions: List[SchedulingDecision] = []
        self.performance_metrics: List[Dict[str, Any]] = []
        
        # Worker管理
        self.worker_factory: Optional[Callable] = None
        self.worker_callback: Optional[Callable] = None
        
        logger.info(f"HybridIntelligentScheduler初始化: "
                   f"模式={execution_mode.value}, "
                   f"会话={self.session_id}")
    
    def _create_default_strategy(self) -> ExecutionStrategy:
        """创建默认执行策略"""
        if self.execution_mode == ExecutionMode.FAST:
            return ExecutionStrategy(
                mode=self.execution_mode,
                initial_workers=1,  # 临时限制为1个worker避免SQLite并发
                max_workers=1,
                min_workers=1,
                scale_up_threshold=0.8,
                scale_down_threshold=0.2,
                monitoring_interval_seconds=15,
                enable_progressive_phases=False
            )
        elif self.execution_mode == ExecutionMode.SMART:
            return ExecutionStrategy(
                mode=self.execution_mode,
                initial_workers=1,  # 临时限制为1个worker避免SQLite并发
                max_workers=1,
                min_workers=1,
                scale_up_threshold=0.6,
                scale_down_threshold=0.3,
                monitoring_interval_seconds=20,
                enable_progressive_phases=False,
                enable_auto_scaling=True
            )
        else:  # AUTO mode
            return ExecutionStrategy(
                mode=self.execution_mode,
                initial_workers=1,  # 临时限制为1个worker避免SQLite并发
                max_workers=1,
                min_workers=1,
                scale_up_threshold=0.7,
                scale_down_threshold=0.3,
                monitoring_interval_seconds=30,
                enable_progressive_phases=True,
                enable_auto_scaling=True
            )
    
    async def analyze_api(self, endpoints: List[EndpointInfo]) -> APIPattern:
        """
        分析API并识别模式
        
        Args:
            endpoints: API端点列表
            
        Returns:
            API模式分析结果
        """
        self.state = SchedulerState.ANALYZING
        self.endpoints = endpoints
        
        logger.info(f"开始分析API: {len(endpoints)}个端点")
        
        # 使用APIPatternMatcher分析
        self.api_pattern = self.pattern_matcher.analyze_api(endpoints)
        
        # 根据分析结果调整策略
        self._adjust_strategy_based_on_pattern()
        
        # 初始化其他组件
        await self._initialize_components()
        
        logger.info(f"API分析完成: 模式={self.api_pattern.pattern_name}, "
                   f"复杂度={self.api_pattern.complexity_metrics.overall_complexity.value}")
        
        return self.api_pattern
    
    def _adjust_strategy_based_on_pattern(self) -> None:
        """根据API模式调整执行策略"""
        if not self.api_pattern:
            return
        
        # 使用模式识别的推荐值更新策略
        if self.execution_mode == ExecutionMode.AUTO:
            self.execution_strategy.initial_workers = self.api_pattern.safe_start_workers
            self.execution_strategy.max_workers = self.api_pattern.recommended_max_workers
            
            # 根据风险因素调整阈值
            if "high_complexity" in self.api_pattern.risk_factors:
                self.execution_strategy.scale_up_threshold = 0.6  # 更积极扩容
                self.execution_strategy.scale_down_threshold = 0.4  # 更保守缩容
        
        logger.info(f"策略调整: workers={self.execution_strategy.initial_workers}-"
                   f"{self.execution_strategy.max_workers}")
    
    async def _initialize_components(self) -> None:
        """初始化调度组件"""
        # 初始化渐进式调度器
        if self.execution_strategy.enable_progressive_phases:
            self.progressive_scheduler = ProgressiveScheduler(
                self.execution_mode,
                self.api_pattern
            )
        
        # 初始化动态扩缩容器
        self.dynamic_scaler = DynamicWorkerScaler(
            min_workers=self.execution_strategy.min_workers,
            max_workers=self.execution_strategy.max_workers,
            scale_up_threshold=self.execution_strategy.scale_up_threshold,
            scale_down_threshold=self.execution_strategy.scale_down_threshold,
            monitoring_interval=self.execution_strategy.monitoring_interval_seconds
        )
    
    async def start(self, worker_factory: Callable, 
                    worker_callback: Optional[Callable] = None) -> None:
        """
        启动智能调度
        
        Args:
            worker_factory: Worker工厂函数
            worker_callback: Worker事件回调函数
        """
        if self.is_running:
            logger.warning("调度器已在运行中")
            return
        
        if not self.api_pattern:
            raise ValueError("请先调用analyze_api分析API")
        
        self.worker_factory = worker_factory
        self.worker_callback = worker_callback
        self.start_time = datetime.now()
        self.state = SchedulerState.RUNNING
        self.is_running = True
        
        logger.info(f"启动智能调度: 模式={self.execution_mode.value}")
        
        # 创建初始Workers
        await self._create_initial_workers()
        
        # 启动调度循环
        self.scheduling_task = asyncio.create_task(self._scheduling_loop())
    
    async def _create_initial_workers(self) -> None:
        """创建初始Workers"""
        initial_count = self.execution_strategy.initial_workers
        logger.info(f"创建初始Workers: {initial_count}个")
        
        for i in range(initial_count):
            worker_id = f"worker_{i+1}"
            worker = await self.worker_factory(worker_id)
            
            if worker:
                # 通知DynamicScaler
                self.dynamic_scaler.workers[worker_id] = worker
                self.dynamic_scaler.update_worker_metrics(
                    worker_id,
                    WorkerMetrics(
                        worker_id=worker_id,
                        status="starting"
                    )
                )
    
    async def _scheduling_loop(self) -> None:
        """调度循环主逻辑"""
        try:
            while self.is_running:
                # 收集Worker指标
                worker_metrics = await self._collect_worker_metrics()
                
                # 更新性能数据
                self._update_performance_data(worker_metrics)
                
                # 获取调度决策
                decision = await self._make_scheduling_decision(worker_metrics)
                
                # 执行调度决策
                if decision.action != ScalingAction.MAINTAIN:
                    await self._execute_decision(decision)
                
                # 记录决策
                self.scheduling_decisions.append(decision)
                
                # 检查是否需要阶段转换
                if self.progressive_scheduler:
                    await self._check_phase_transition(worker_metrics)
                
                # 等待下一个监控周期
                await asyncio.sleep(self.execution_strategy.monitoring_interval_seconds)
                
        except asyncio.CancelledError:
            logger.info("调度循环被取消")
        except Exception as e:
            logger.error(f"调度循环异常: {str(e)}")
            self.state = SchedulerState.STOPPED
        finally:
            self.is_running = False
    
    async def _make_scheduling_decision(self, 
                                      worker_metrics: List[WorkerMetrics]) -> SchedulingDecision:
        """
        融合多个调度器的决策建议
        
        Args:
            worker_metrics: Worker指标列表
            
        Returns:
            最终的调度决策
        """
        decisions = []
        
        # 1. 获取动态扩缩容器的建议
        if self.execution_strategy.enable_auto_scaling:
            dynamic_decision = await self.dynamic_scaler.evaluate_scaling_need()
            decisions.append(("dynamic", dynamic_decision))
        
        # 2. 获取渐进式调度器的建议
        if self.progressive_scheduler:
            progressive_decision = self.progressive_scheduler.get_scaling_recommendation()
            decisions.append(("progressive", progressive_decision))
        
        # 3. 融合决策
        if not decisions:
            # 没有调度器，保持现状
            return SchedulingDecision(
                action=ScalingAction.MAINTAIN,
                current_workers=len(worker_metrics),
                target_workers=len(worker_metrics),
                reason="No scheduler available",
                confidence=1.0,
                estimated_impact={}
            )
        
        return self._fuse_decisions(decisions, worker_metrics)
    
    def _fuse_decisions(self, decisions: List[Tuple[str, SchedulingDecision]], 
                       worker_metrics: List[WorkerMetrics]) -> SchedulingDecision:
        """
        融合多个调度决策
        
        Args:
            decisions: (调度器名称, 决策)列表
            worker_metrics: Worker指标
            
        Returns:
            融合后的决策
        """
        if len(decisions) == 1:
            # 只有一个决策，直接返回
            return decisions[0][1]
        
        # 提取各个决策
        dynamic_decision = None
        progressive_decision = None
        
        for name, decision in decisions:
            if name == "dynamic":
                dynamic_decision = decision
            elif name == "progressive":
                progressive_decision = decision
        
        # 融合规则
        if self.execution_mode == ExecutionMode.AUTO:
            # AUTO模式：渐进式调度器优先
            if progressive_decision:
                # 但要考虑动态调度器的资源限制
                if (dynamic_decision and 
                    dynamic_decision.action == ScalingAction.SCALE_DOWN and
                    progressive_decision.action == ScalingAction.SCALE_UP):
                    # 资源受限，采用保守策略
                    return SchedulingDecision(
                        action=ScalingAction.MAINTAIN,
                        current_workers=progressive_decision.current_workers,
                        target_workers=progressive_decision.current_workers,
                        reason="Resource constraints prevent scaling up",
                        confidence=0.7,
                        estimated_impact={
                            "conflict": "progressive wants up, dynamic wants down"
                        }
                    )
                return progressive_decision
        
        elif self.execution_mode == ExecutionMode.SMART:
            # SMART模式：动态调度器优先
            if dynamic_decision:
                return dynamic_decision
        
        # 默认：选择置信度最高的决策
        best_decision = max(decisions, key=lambda x: x[1].confidence)[1]
        return best_decision
    
    async def _execute_decision(self, decision: SchedulingDecision) -> None:
        """执行调度决策"""
        success = await self.dynamic_scaler.execute_scaling(
            decision, 
            self.worker_factory
        )
        
        if success and self.worker_callback:
            # 通知外部系统
            await self.worker_callback("scaling", {
                "action": decision.action.value,
                "from_workers": decision.current_workers,
                "to_workers": decision.target_workers,
                "reason": decision.reason
            })
    
    async def _collect_worker_metrics(self) -> List[WorkerMetrics]:
        """收集Worker指标"""
        metrics = []
        
        for worker_id, worker in self.dynamic_scaler.workers.items():
            # 这里需要根据实际Worker实现获取指标
            # 暂时使用模拟数据
            metric = WorkerMetrics(
                worker_id=worker_id,
                status="running" if hasattr(worker, 'is_running') and worker.is_running else "idle",
                tasks_completed=getattr(worker, 'tasks_completed', 0),
                tasks_failed=getattr(worker, 'tasks_failed', 0),
                avg_task_duration_seconds=getattr(worker, 'avg_duration', 1.0),
                queue_size=getattr(worker, 'queue_size', 0),
                pending_tasks=getattr(worker, 'pending_tasks', 0)
            )
            
            metrics.append(metric)
            # 更新到DynamicScaler
            self.dynamic_scaler.update_worker_metrics(worker_id, metric)
        
        return metrics
    
    def _update_performance_data(self, worker_metrics: List[WorkerMetrics]) -> None:
        """更新性能数据"""
        # 更新渐进式调度器
        if self.progressive_scheduler:
            self.progressive_scheduler.update_performance_metrics(worker_metrics)
        
        # 记录性能指标
        total_completed = sum(m.tasks_completed for m in worker_metrics)
        total_failed = sum(m.tasks_failed for m in worker_metrics)
        avg_duration = sum(m.avg_task_duration_seconds * m.tasks_completed 
                          for m in worker_metrics) / max(total_completed, 1)
        
        self.performance_metrics.append({
            "timestamp": datetime.now(),
            "total_completed": total_completed,
            "total_failed": total_failed,
            "avg_duration": avg_duration,
            "active_workers": sum(1 for m in worker_metrics if m.status == "running"),
            "queue_size": sum(m.queue_size for m in worker_metrics)
        })
        
        # 限制历史数据大小
        if len(self.performance_metrics) > 1000:
            self.performance_metrics = self.performance_metrics[-1000:]
    
    async def _check_phase_transition(self, worker_metrics: List[WorkerMetrics]) -> None:
        """检查是否需要阶段转换"""
        if not self.progressive_scheduler:
            return
        
        if self.progressive_scheduler.should_transition(worker_metrics):
            success = self.progressive_scheduler.transition_to_next_phase()
            
            if success and self.worker_callback:
                phase = self.progressive_scheduler.get_current_phase()
                await self.worker_callback("phase_transition", {
                    "new_phase": phase.phase_name if phase else "unknown",
                    "target_workers": phase.target_workers if phase else 0
                })
    
    async def stop(self) -> None:
        """停止调度器"""
        logger.info("停止智能调度器")
        
        self.state = SchedulerState.STOPPING
        self.is_running = False
        
        # 取消调度任务
        if self.scheduling_task:
            self.scheduling_task.cancel()
            try:
                await self.scheduling_task
            except asyncio.CancelledError:
                pass
        
        # 清理Workers
        await self.dynamic_scaler.cleanup()
        
        self.state = SchedulerState.STOPPED
        logger.info("智能调度器已停止")
    
    def get_current_status(self) -> Dict[str, Any]:
        """获取当前调度状态"""
        return {
            "state": self.state.value,
            "session_id": self.session_id,
            "execution_mode": self.execution_mode.value,
            "api_pattern": {
                "name": self.api_pattern.pattern_name if self.api_pattern else None,
                "complexity": self.api_pattern.complexity_metrics.overall_complexity.value 
                            if self.api_pattern else None
            },
            "current_phase": self.progressive_scheduler.get_current_phase().phase_name 
                           if self.progressive_scheduler and self.progressive_scheduler.get_current_phase() 
                           else None,
            "workers": self.dynamic_scaler.get_scaling_summary() if self.dynamic_scaler else {},
            "performance": self.performance_metrics[-1] if self.performance_metrics else None
        }
    
    def generate_report(self) -> SchedulingReport:
        """生成调度报告"""
        end_time = datetime.now() if self.start_time else None
        
        # 计算执行统计
        total_completed = 0
        total_failed = 0
        if self.performance_metrics:
            last_metrics = self.performance_metrics[-1]
            total_completed = last_metrics.get("total_completed", 0)
            total_failed = last_metrics.get("total_failed", 0)
        
        # 计算Worker统计
        peak_workers = 0
        worker_utilization_sum = 0
        utilization_count = 0
        
        for metrics in self.performance_metrics:
            active = metrics.get("active_workers", 0)
            peak_workers = max(peak_workers, active)
            
            if active > 0:
                # 简化的利用率计算
                queue_size = metrics.get("queue_size", 0)
                utilization = min(1.0, queue_size / (active * 10))  # 假设每个worker容量为10
                worker_utilization_sum += utilization
                utilization_count += 1
        
        avg_utilization = worker_utilization_sum / max(utilization_count, 1)
        
        # 计算性能指标
        total_endpoints = len(self.endpoints) if self.endpoints else 0
        avg_processing_time = 0
        throughput = 0
        
        if self.start_time and end_time and total_completed > 0:
            total_time = (end_time - self.start_time).total_seconds()
            avg_processing_time = total_time / total_completed
            throughput = (total_completed / total_time) * 60  # 每分钟
        
        # 评估智能调度效果
        pattern_accuracy = 0.9 if self.api_pattern else 0  # 简化评估
        
        # 统计扩缩容事件
        scaling_events = len([d for d in self.scheduling_decisions 
                            if d.action != ScalingAction.MAINTAIN])
        
        # 计算推荐vs实际的方差
        recommended_workers = self.api_pattern.optimal_workers if self.api_pattern else 3
        actual_avg_workers = sum(m.get("active_workers", 0) 
                               for m in self.performance_metrics) / max(len(self.performance_metrics), 1)
        variance = abs(recommended_workers - actual_avg_workers) / recommended_workers if recommended_workers > 0 else 0
        
        report = SchedulingReport(
            session_id=self.session_id,
            execution_mode=self.execution_mode,
            start_time=self.start_time or datetime.now(),
            end_time=end_time,
            total_endpoints=total_endpoints,
            completed_endpoints=total_completed,
            failed_endpoints=total_failed,
            total_test_cases_generated=total_completed * 6,  # 假设每个端点6个测试用例
            peak_workers=peak_workers,
            worker_utilization_avg=avg_utilization,
            total_scaling_events=scaling_events,
            avg_endpoint_processing_time=avg_processing_time,
            total_execution_time_seconds=(end_time - self.start_time).total_seconds() 
                                       if self.start_time and end_time else 0,
            throughput_endpoints_per_minute=throughput,
            scheduling_decisions=self.scheduling_decisions[-10:],  # 最后10个决策
            pattern_detection_accuracy=pattern_accuracy,
            recommended_vs_actual_variance=variance
        )
        
        return report
    
    def get_real_time_metrics(self) -> Dict[str, Any]:
        """获取实时监控指标"""
        current_status = self.get_current_status()
        
        # 添加实时性能指标
        if self.performance_metrics:
            recent_metrics = self.performance_metrics[-5:]  # 最近5个数据点
            
            # 计算趋势
            if len(recent_metrics) >= 2:
                throughput_trend = []
                for i in range(1, len(recent_metrics)):
                    prev = recent_metrics[i-1]["total_completed"]
                    curr = recent_metrics[i]["total_completed"]
                    delta = curr - prev
                    throughput_trend.append(delta)
                
                current_status["throughput_trend"] = throughput_trend
                current_status["avg_throughput"] = sum(throughput_trend) / len(throughput_trend)
        
        # 添加队列压力
        if self.dynamic_scaler:
            current_status["queue_pressure"] = self.dynamic_scaler._calculate_queue_pressure()
        
        # 添加阶段进度
        if self.progressive_scheduler:
            current_status["phase_progress"] = self.progressive_scheduler._calculate_phase_progress()
        
        return current_status