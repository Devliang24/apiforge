"""
API模式识别器

负责分析OpenAPI规范，识别API模式，评估复杂度，并给出智能推荐配置。
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict, Counter
import statistics

from apiforge.scheduling.models import (
    APIPattern,
    ComplexityMetrics,
    APIComplexityLevel
)
from apiforge.parser.spec_parser import EndpointInfo
from apiforge.logger import logger


class APIPatternMatcher:
    """API模式识别器"""
    
    def __init__(self):
        """初始化模式识别器"""
        # 定义常见的API模式特征
        self.pattern_signatures = {
            "RESTful CRUD": {
                "required_methods": ["GET", "POST", "PUT", "DELETE"],
                "path_patterns": [
                    r"/\w+/?$",              # /users
                    r"/\w+/\{\w+\}/?$"       # /users/{id}
                ],
                "features": ["id_in_path", "standard_methods"]
            },
            "GraphQL": {
                "required_methods": ["POST"],
                "path_patterns": [r"/graphql/?$"],
                "features": ["single_endpoint", "query_in_body"]
            },
            "RPC-style": {
                "required_methods": ["POST"],
                "path_patterns": [r"/\w+/\w+"],  # /service/action
                "features": ["action_in_path", "post_dominant"]
            },
            "REST-like": {
                "required_methods": ["GET", "POST"],
                "path_patterns": [r"/api/\w+"],
                "features": ["partial_rest", "mixed_patterns"]
            },
            "Microservice": {
                "required_methods": ["GET", "POST", "PUT", "DELETE"],
                "path_patterns": [r"/api/v\d+/\w+"],
                "features": ["versioned", "domain_focused"]
            }
        }
        
        # 复杂度权重配置
        self.complexity_weights = {
            "endpoint_count": 0.25,
            "parameter_complexity": 0.20,
            "auth_complexity": 0.15,
            "schema_depth": 0.20,
            "method_diversity": 0.10,
            "business_dependency": 0.10
        }
        
        # 历史成功率数据（模拟）
        self.historical_success_rates = {
            "RESTful CRUD": {"2_workers": 0.85, "3_workers": 0.92, "4_workers": 0.95},
            "GraphQL": {"2_workers": 0.88, "3_workers": 0.90, "4_workers": 0.91},
            "RPC-style": {"2_workers": 0.82, "3_workers": 0.88, "4_workers": 0.90},
            "REST-like": {"2_workers": 0.80, "3_workers": 0.87, "4_workers": 0.89},
            "Microservice": {"2_workers": 0.83, "3_workers": 0.90, "4_workers": 0.93}
        }
    
    def analyze_api(self, endpoints: List[EndpointInfo]) -> APIPattern:
        """
        分析API并返回模式识别结果
        
        Args:
            endpoints: 端点信息列表
            
        Returns:
            APIPattern: API模式识别结果
        """
        logger.info(f"开始分析API模式，共{len(endpoints)}个端点")
        
        # 1. 计算复杂度指标
        complexity_metrics = self._calculate_complexity_metrics(endpoints)
        
        # 2. 识别API模式
        pattern_name, confidence = self._identify_pattern(endpoints)
        
        # 3. 基于模式和复杂度推荐配置
        recommendations = self._calculate_recommendations(
            pattern_name, 
            complexity_metrics
        )
        
        # 4. 检测特性和风险因素
        detected_features = self._detect_features(endpoints)
        risk_factors = self._identify_risk_factors(endpoints, complexity_metrics)
        
        # 5. 获取历史数据支持
        similar_apis_count = self._get_similar_apis_count(pattern_name, complexity_metrics)
        success_rate = self._get_success_rate(pattern_name, recommendations["optimal_workers"])
        
        # 构建结果
        result = APIPattern(
            pattern_name=pattern_name,
            confidence_score=confidence,
            complexity_metrics=complexity_metrics,
            safe_start_workers=recommendations["safe_start_workers"],
            recommended_max_workers=recommendations["recommended_max_workers"],
            optimal_workers=recommendations["optimal_workers"],
            similar_apis_count=similar_apis_count,
            success_rate_with_recommended=success_rate,
            detected_features=detected_features,
            risk_factors=risk_factors
        )
        
        logger.info(f"API模式识别完成: {pattern_name} (置信度: {confidence:.2f})")
        return result
    
    def _calculate_complexity_metrics(self, endpoints: List[EndpointInfo]) -> ComplexityMetrics:
        """计算API复杂度指标"""
        # 统计方法分布
        method_distribution = defaultdict(int)
        for endpoint in endpoints:
            method_distribution[endpoint.method] += 1
        
        # 计算参数复杂度
        param_scores = []
        for endpoint in endpoints:
            score = 0
            # 路径参数
            score += len(endpoint.path_parameters) * 1.0
            # 查询参数
            score += len(endpoint.query_parameters) * 0.8
            # 请求体复杂度
            if endpoint.request_body:
                score += self._calculate_schema_complexity(endpoint.request_body) * 1.5
            param_scores.append(score)
        
        avg_param_complexity = statistics.mean(param_scores) if param_scores else 0.0
        
        # 计算认证复杂度
        auth_complexity = self._calculate_auth_complexity(endpoints)
        
        # 计算schema深度
        schema_depths = []
        for endpoint in endpoints:
            if endpoint.request_body:
                depth = self._calculate_schema_depth(endpoint.request_body)
                schema_depths.append(depth)
            # 处理响应schema
            for response in endpoint.responses:
                if hasattr(response, 'content') and response.content:
                    # 简化处理：假设schema深度为2
                    schema_depths.append(2)
        
        avg_schema_depth = statistics.mean(schema_depths) if schema_depths else 1.0
        
        # 计算业务依赖复杂度
        business_dependency = self._calculate_business_dependency(endpoints)
        
        # 确定整体复杂度级别
        overall_complexity = self._determine_complexity_level(
            len(endpoints),
            avg_param_complexity,
            auth_complexity,
            avg_schema_depth,
            business_dependency
        )
        
        # 估算每个端点的测试用例数和总处理时间
        test_cases_per_endpoint = self._estimate_test_cases_per_endpoint(overall_complexity)
        total_time = self._estimate_processing_time(len(endpoints), overall_complexity)
        
        return ComplexityMetrics(
            endpoint_count=len(endpoints),
            method_distribution=dict(method_distribution),
            parameter_complexity_score=min(avg_param_complexity, 10.0),
            auth_complexity_score=auth_complexity,
            schema_depth_avg=avg_schema_depth,
            business_dependency_score=business_dependency,
            overall_complexity=overall_complexity,
            estimated_test_cases_per_endpoint=test_cases_per_endpoint,
            estimated_total_processing_time_minutes=total_time
        )
    
    # 辅助方法实现
    def _calculate_schema_complexity(self, schema: Dict[str, Any]) -> float:
        """计算schema复杂度"""
        if not schema:
            return 0.0
        
        complexity = 0.0
        
        # 基于属性数量
        if "properties" in schema:
            complexity += len(schema["properties"]) * 0.5
        
        # 基于必需字段
        if "required" in schema:
            complexity += len(schema["required"]) * 0.3
        
        # 基于嵌套对象
        if "properties" in schema:
            for prop in schema["properties"].values():
                if isinstance(prop, dict) and prop.get("type") == "object":
                    complexity += 1.0
                elif isinstance(prop, dict) and prop.get("type") == "array":
                    complexity += 0.8
        
        return min(complexity, 10.0)
    
    def _calculate_auth_complexity(self, endpoints: List[EndpointInfo]) -> float:
        """计算认证复杂度"""
        auth_types = set()
        secured_endpoints = 0
        
        for endpoint in endpoints:
            if endpoint.security:
                secured_endpoints += 1
                # 简化处理：统计不同的安全需求
                auth_types.update(str(endpoint.security))
        
        if not endpoints:
            return 0.0
        
        # 基于安全端点比例和认证类型多样性
        security_ratio = secured_endpoints / len(endpoints)
        diversity_score = len(auth_types) * 2.0
        
        return min((security_ratio * 5.0) + diversity_score, 10.0)
    
    def _calculate_schema_depth(self, schema: Dict[str, Any], current_depth: int = 0) -> int:
        """递归计算schema最大深度"""
        if not isinstance(schema, dict):
            return current_depth
        
        max_depth = current_depth
        
        # 检查properties
        if "properties" in schema:
            for prop in schema["properties"].values():
                if isinstance(prop, dict):
                    depth = self._calculate_schema_depth(prop, current_depth + 1)
                    max_depth = max(max_depth, depth)
        
        # 检查items (for arrays)
        if "items" in schema and isinstance(schema["items"], dict):
            depth = self._calculate_schema_depth(schema["items"], current_depth + 1)
            max_depth = max(max_depth, depth)
        
        return max_depth
    
    def _calculate_business_dependency(self, endpoints: List[EndpointInfo]) -> float:
        """计算业务依赖复杂度"""
        # 基于路径深度和相互引用估算
        path_depths = []
        unique_resources = set()
        
        for endpoint in endpoints:
            # 计算路径深度
            depth = len([p for p in endpoint.path.split('/') if p and not p.startswith('{')])
            path_depths.append(depth)
            
            # 提取资源名称
            parts = endpoint.path.split('/')
            for part in parts:
                if part and not part.startswith('{') and not part.startswith('v'):
                    unique_resources.add(part)
        
        avg_depth = statistics.mean(path_depths) if path_depths else 0
        resource_complexity = len(unique_resources) * 0.5
        
        return min(avg_depth + resource_complexity, 10.0)
    
    def _determine_complexity_level(self, endpoint_count: int, param_complexity: float,
                                  auth_complexity: float, schema_depth: float,
                                  business_dependency: float) -> APIComplexityLevel:
        """确定整体复杂度级别"""
        # 加权计算总分
        weighted_score = (
            endpoint_count * 0.002 +  # 每个端点贡献0.002分
            param_complexity * self.complexity_weights["parameter_complexity"] +
            auth_complexity * self.complexity_weights["auth_complexity"] +
            schema_depth * self.complexity_weights["schema_depth"] +
            business_dependency * self.complexity_weights["business_dependency"]
        )
        
        # 基于端点数量的初步分类
        if endpoint_count <= 20:
            base_level = APIComplexityLevel.SIMPLE
        elif endpoint_count <= 50:
            base_level = APIComplexityLevel.MEDIUM
        elif endpoint_count <= 100:
            base_level = APIComplexityLevel.COMPLEX
        else:
            base_level = APIComplexityLevel.VERY_COMPLEX
        
        # 基于加权分数调整
        if weighted_score < 3.0:
            return APIComplexityLevel.SIMPLE
        elif weighted_score < 5.0:
            return max(base_level, APIComplexityLevel.MEDIUM)
        elif weighted_score < 7.0:
            return max(base_level, APIComplexityLevel.COMPLEX)
        else:
            return APIComplexityLevel.VERY_COMPLEX
    
    def _estimate_test_cases_per_endpoint(self, complexity: APIComplexityLevel) -> int:
        """估算每个端点的测试用例数"""
        estimates = {
            APIComplexityLevel.SIMPLE: 5,
            APIComplexityLevel.MEDIUM: 6,
            APIComplexityLevel.COMPLEX: 8,
            APIComplexityLevel.VERY_COMPLEX: 10
        }
        return estimates.get(complexity, 6)
    
    def _estimate_processing_time(self, endpoint_count: int, 
                                complexity: APIComplexityLevel) -> float:
        """估算总处理时间（分钟）"""
        # 基础时间：每个端点的平均处理时间
        base_times = {
            APIComplexityLevel.SIMPLE: 0.5,      # 30秒
            APIComplexityLevel.MEDIUM: 0.8,      # 48秒
            APIComplexityLevel.COMPLEX: 1.2,     # 72秒
            APIComplexityLevel.VERY_COMPLEX: 1.8 # 108秒
        }
        
        base_time = base_times.get(complexity, 0.8)
        
        # 考虑规模效应（并发处理）
        if endpoint_count > 50:
            scale_factor = 0.7  # 大规模时效率提升
        else:
            scale_factor = 0.9
        
        return round(endpoint_count * base_time * scale_factor, 1)
    
    def _identify_pattern(self, endpoints: List[EndpointInfo]) -> Tuple[str, float]:
        """识别API模式"""
        pattern_scores = {}
        
        # 提取端点特征
        methods = [ep.method for ep in endpoints]
        paths = [ep.path for ep in endpoints]
        method_counter = Counter(methods)
        
        # 对每个模式进行评分
        for pattern_name, signature in self.pattern_signatures.items():
            score = 0.0
            match_count = 0
            
            # 检查必需的HTTP方法
            required_methods = set(signature["required_methods"])
            available_methods = set(method_counter.keys())
            method_coverage = len(required_methods & available_methods) / len(required_methods)
            score += method_coverage * 0.4
            if method_coverage > 0:
                match_count += 1
            
            # 检查路径模式
            path_matches = 0
            for path in paths:
                for pattern in signature["path_patterns"]:
                    if re.match(pattern, path):
                        path_matches += 1
                        break
            
            if paths:
                path_score = min(path_matches / len(paths), 1.0)
                score += path_score * 0.3
                if path_score > 0.3:
                    match_count += 1
            
            # 检查特性
            features = self._extract_endpoint_features(endpoints)
            feature_matches = len(set(signature["features"]) & set(features))
            if signature["features"]:
                feature_score = feature_matches / len(signature["features"])
                score += feature_score * 0.3
                if feature_score > 0.5:
                    match_count += 1
            
            # 计算置信度
            confidence = score * (match_count / 3.0)
            pattern_scores[pattern_name] = confidence
        
        # 选择最佳匹配
        if pattern_scores:
            best_pattern = max(pattern_scores.items(), key=lambda x: x[1])
            pattern_name, confidence = best_pattern
            
            # 如果置信度太低，返回通用模式
            if confidence < 0.3:
                return "Generic API", 0.5
            
            return pattern_name, confidence
        
        return "Generic API", 0.5
    
    def _extract_endpoint_features(self, endpoints: List[EndpointInfo]) -> List[str]:
        """提取端点特征用于模式匹配"""
        features = []
        
        # 检查是否有ID在路径中
        if any('{' in ep.path and '}' in ep.path for ep in endpoints):
            features.append("id_in_path")
        
        # 检查是否使用标准HTTP方法
        standard_methods = {"GET", "POST", "PUT", "DELETE", "PATCH"}
        used_methods = {ep.method for ep in endpoints}
        if used_methods.issubset(standard_methods):
            features.append("standard_methods")
        
        # 检查是否是单一端点（GraphQL特征）
        unique_paths = {ep.path for ep in endpoints}
        if len(unique_paths) == 1:
            features.append("single_endpoint")
        
        # 检查POST是否占主导
        method_counts = Counter(ep.method for ep in endpoints)
        if method_counts.get("POST", 0) > len(endpoints) * 0.7:
            features.append("post_dominant")
        
        # 检查是否有版本号
        if any("/v" in ep.path and any(c.isdigit() for c in ep.path) for ep in endpoints):
            features.append("versioned")
        
        # 检查动作是否在路径中（RPC特征）
        if any(len(ep.path.split('/')) > 3 and ep.method == "POST" for ep in endpoints):
            features.append("action_in_path")
        
        return features
    
    def _calculate_recommendations(self, pattern_name: str, 
                                 complexity: ComplexityMetrics) -> Dict[str, int]:
        """基于模式和复杂度计算推荐配置"""
        # 基础推荐值
        base_recommendations = {
            "RESTful CRUD": {"safe": 2, "optimal": 3, "max": 5},
            "GraphQL": {"safe": 2, "optimal": 3, "max": 4},
            "RPC-style": {"safe": 2, "optimal": 3, "max": 5},
            "REST-like": {"safe": 2, "optimal": 3, "max": 5},
            "Microservice": {"safe": 2, "optimal": 4, "max": 6},
            "Generic API": {"safe": 2, "optimal": 3, "max": 5}
        }
        
        base = base_recommendations.get(pattern_name, base_recommendations["Generic API"])
        
        # 基于复杂度调整
        if complexity.overall_complexity == APIComplexityLevel.SIMPLE:
            adjustment = 0
        elif complexity.overall_complexity == APIComplexityLevel.MEDIUM:
            adjustment = 1
        elif complexity.overall_complexity == APIComplexityLevel.COMPLEX:
            adjustment = 2
        else:  # VERY_COMPLEX
            adjustment = 3
        
        # 基于端点数量的额外调整
        if complexity.endpoint_count > 100:
            adjustment += 2
        elif complexity.endpoint_count > 50:
            adjustment += 1
        
        return {
            "safe_start_workers": base["safe"],
            "optimal_workers": min(base["optimal"] + adjustment, base["max"]),
            "recommended_max_workers": min(base["max"] + adjustment, 10)
        }
    
    def _detect_features(self, endpoints: List[EndpointInfo]) -> List[str]:
        """检测API特性"""
        features = []
        
        # 检查分页
        if any("page" in str(ep.query_parameters) or "limit" in str(ep.query_parameters) 
               for ep in endpoints):
            features.append("pagination")
        
        # 检查过滤
        if any("filter" in str(ep.query_parameters) or "search" in str(ep.query_parameters)
               for ep in endpoints):
            features.append("filtering")
        
        # 检查认证
        if any(ep.security for ep in endpoints):
            features.append("authentication")
        
        # 检查文件上传
        if any("multipart" in str(ep.request_body) for ep in endpoints if ep.request_body):
            features.append("file_upload")
        
        # 检查批量操作
        if any("batch" in ep.path or "bulk" in ep.path for ep in endpoints):
            features.append("batch_operations")
        
        # 检查websocket
        if any("ws" in ep.path or "websocket" in ep.path for ep in endpoints):
            features.append("websocket")
        
        return features
    
    def _identify_risk_factors(self, endpoints: List[EndpointInfo], 
                             complexity: ComplexityMetrics) -> List[str]:
        """识别风险因素"""
        risks = []
        
        # 高复杂度
        if complexity.overall_complexity in [APIComplexityLevel.COMPLEX, 
                                           APIComplexityLevel.VERY_COMPLEX]:
            risks.append("high_complexity")
        
        # 大量端点
        if complexity.endpoint_count > 100:
            risks.append("large_api_surface")
        
        # 深层嵌套
        if complexity.schema_depth_avg > 5:
            risks.append("deep_nesting")
        
        # 高参数复杂度
        if complexity.parameter_complexity_score > 7:
            risks.append("complex_parameters")
        
        # 认证复杂
        if complexity.auth_complexity_score > 7:
            risks.append("complex_authentication")
        
        # 方法分布不均
        method_counts = list(complexity.method_distribution.values())
        if method_counts and max(method_counts) / sum(method_counts) > 0.7:
            risks.append("unbalanced_methods")
        
        return risks
    
    def _get_similar_apis_count(self, pattern_name: str, 
                               complexity: ComplexityMetrics) -> int:
        """获取相似API的数量（模拟历史数据）"""
        # 实际实现中，这里应该查询历史数据库
        # 现在返回模拟数据
        base_counts = {
            "RESTful CRUD": 150,
            "GraphQL": 45,
            "RPC-style": 80,
            "REST-like": 120,
            "Microservice": 95,
            "Generic API": 200
        }
        
        base = base_counts.get(pattern_name, 50)
        
        # 基于复杂度调整
        if complexity.overall_complexity == APIComplexityLevel.SIMPLE:
            return int(base * 1.2)
        elif complexity.overall_complexity == APIComplexityLevel.VERY_COMPLEX:
            return int(base * 0.6)
        
        return base
    
    def _get_success_rate(self, pattern_name: str, worker_count: int) -> float:
        """获取推荐配置的成功率"""
        if pattern_name not in self.historical_success_rates:
            return 0.85  # 默认成功率
        
        rates = self.historical_success_rates[pattern_name]
        worker_key = f"{worker_count}_workers"
        
        if worker_key in rates:
            return rates[worker_key]
        
        # 插值计算
        if worker_count < 2:
            return 0.75
        elif worker_count > 4:
            return min(rates.get("4_workers", 0.90) + (worker_count - 4) * 0.01, 0.98)
        
        return 0.85