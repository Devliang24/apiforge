# APIForge

**Enterprise-grade API test case generator from OpenAPI specifications**

APIForge automatically analyzes your OpenAPI/Swagger specifications and generates comprehensive, structured test cases covering positive, negative, and boundary scenarios using Large Language Models (LLMs).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

[English](#english) | [中文](#中文)

## English

## 🌟 Features

- **Automated Test Case Generation**: Generate comprehensive test cases from OpenAPI/Swagger specifications
- **Multiple LLM Providers**: Support for OpenAI, Custom APIs, and Qwen (with /no_think optimization for 10x speed)
- **Enterprise-Grade Architecture**: Async-first design with robust error handling and retry logic
- **Advanced Test Design Methods**: 
  - Boundary Value Analysis (BVA) - Test edge cases and limits
  - Decision Tables - Cover all logical combinations
  - State Transition - Test API state changes
  - Pairwise Testing - Optimize test combinations
  - Equivalence Partitioning - Group similar test scenarios
- **Enhanced Test Coverage**: Generates 5-20 test cases per endpoint using multiple testing strategies
- **Intelligent Task Scheduling**: 
  - SQLite-based persistent task queue
  - Dynamic worker scaling based on load
  - Progressive scheduling with API pattern matching
  - Hybrid scheduling with real-time optimization
- **Web-based Monitoring Dashboard**: 
  - Real-time progress tracking with WebSocket
  - Session management and history
  - Task retry and error tracking
  - Performance metrics and statistics
  - Export reports (CSV/JSON)
- **Multiple Output Formats**: 
  - JSON with standardized schema
  - CSV for spreadsheet tools and test management systems
  - Intermediate files for debugging
- **Production-Ready Features**:
  - Robust error handling and automatic retries
  - Rate limiting and concurrency control
  - Memory-efficient processing for large APIs
  - Graceful shutdown and task persistence
- **Extensible Provider System**: Easy to add support for new LLM providers
- **Security-First**: Secure handling of API keys and sensitive information
- **Rich CLI Interface**: Beautiful command-line interface with progress indicators

## 🚀 Quick Start

### 📦 Installation

```bash
# Clone the repository
git clone https://github.com/apiforge/apiforge.git
cd apiforge

# Install dependencies
pip install -e .
```

### ⚙️ Configuration

1. Copy the environment template:
```bash
cp .env.example .env
```

2. Configure your preferred LLM provider:

**For Qwen (Default - Fast & Free):**
```bash
LLM_PROVIDER=qwen
# No API key required, uses default endpoint
```

**For OpenAI:**
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-api-key-here
```

**For Custom API:**
```bash
LLM_PROVIDER=custom
CUSTOM_API_KEY=your-api-key
CUSTOM_BASE_URL=https://your-api.com/v1
CUSTOM_MODEL=your-model-name
```

### 🎯 Basic Usage

Generate test cases from an OpenAPI specification:

```bash
# Basic usage (uses default Qwen provider)
python run.py --url https://petstore.swagger.io/v2/swagger.json --output petstore_tests.json

# Generate test cases in CSV format for spreadsheet tools
python run.py --url https://petstore.swagger.io/v2/swagger.json --output petstore_tests.csv

# With intermediate file outputs for debugging
python run.py --url https://api.example.com/spec.json --output tests.json --intermediate

# Using a specific provider
python run.py --url https://api.example.com/spec.json --output tests.json --provider openai

# Run with different execution modes
python run.py --url https://api.example.com/spec.json --output tests.json --mode auto
# Available modes: auto (intelligent progressive), fast (maximum concurrency), 
#                  smart (dynamic scheduling), ai-analysis (AI-powered deep analysis)
```

### 📊 Monitoring Dashboard

APIForge includes a powerful monitoring dashboard for tracking test generation progress:

```bash
# Start the monitoring dashboard standalone
python run.py dashboard

# Or run generation with automatic monitoring
python run.py --url https://api.example.com/spec.json --output tests.json --monitor
```

Access the dashboard at:
- **Main Dashboard**: http://localhost:9099
- **Real-time Monitor**: http://localhost:9099/monitor
- **Error Logs**: http://localhost:9099/errors
- **Statistics**: http://localhost:9099/statistics

Features:
- Real-time progress tracking with WebSocket updates
- Session history and management
- Task status monitoring with retry capabilities
- Performance metrics and statistics
- Error tracking and analysis
- Export functionality for reports (CSV/JSON)

### 💻 Programmatic Usage

```python
import asyncio
from apiforge.orchestrator import run_generation

async def generate_tests():
    await run_generation(
        url="https://petstore.swagger.io/v2/swagger.json",
        output_path="test_suite.json"
    )

asyncio.run(generate_tests())
```

## 📖 Documentation

### 💡 Command Line Interface

```bash
# Generate test cases
python run.py --url <OPENAPI_URL> --output <OUTPUT_FILE> [OPTIONS]

# Show system information
python run.py info 

# Available options:
#   --url, -u          URL of OpenAPI specification (required)
#   --output, -o       Output file path (.json or .csv) (required)
#   --verbose, -v      Enable verbose logging
#   --provider, -p     LLM provider to use (default: qwen)
#   --intermediate     Save intermediate processing files
#   --mode, -m         Execution mode: auto|fast|smart|ai-analysis (default: auto)
#   --monitor, -M      Enable real-time monitoring dashboard
#   --help            Show help message

# Generate CSV template for manual test creation
python generate_csv_template.py --output test_template.csv
```

### ⚙️ Configuration Options

All configuration can be set via environment variables in your `.env` file:

```env
# OpenAI Configuration
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4
OPENAI_MAX_TOKENS=4000
OPENAI_TEMPERATURE=0.1

# Performance Settings
MAX_CONCURRENT_REQUESTS=10
RATE_LIMIT_PER_MINUTE=100

# Output Settings
OUTPUT_FORMAT=json
OUTPUT_INDENT=2
VALIDATE_OUTPUT=true

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=structured
```

### 💾 Output Formats

APITestGen supports multiple output formats:

#### JSON Format (Default)

Generates test suites in a standardized JSON format:

```json
{
  "testSuite": {
    "name": "API Test Suite",
    "description": "Automatically generated test suite",
    "baseUrl": "https://api.example.com",
    "testCases": [
      {
        "id": "TC_001",
        "name": "Create user with valid data",
        "description": "Verify successful user creation",
        "priority": "High",
        "category": "positive",
        "tags": ["users", "create"],
        "request": {
          "method": "POST",
          "endpoint": "/v1/users",
          "headers": {"Content-Type": "application/json"},
          "pathParams": {},
          "queryParams": {},
          "body": {"name": "John Doe", "email": "john@example.com"}
        },
        "expectedResponse": {
          "statusCode": 201,
          "headers": {"Content-Type": "application/json"},
          "bodySchema": {"type": "object", "properties": {...}}
        },
        "preconditions": "System is running",
        "postconditions": "User record created"
      }
    ]
  }
}
```

#### CSV Format

Export test cases in CSV format for use with spreadsheet software or test management tools:

```csv
test_id,test_name,endpoint,method,priority,category,path_params,query_params,headers,request_body,expected_status,expected_headers,expected_body,description,preconditions,postconditions,tags
TC_001,Create user with valid data,/v1/users,POST,High,positive,,,"{"Content-Type":"application/json"}","{"name":"John Doe","email":"john@example.com"}",201,"Content-Type=application/json","{"type":"object"}",Verify successful user creation,System is running,User record created,"users,create"
```

Features:
- Compatible with Excel, Google Sheets, and test management tools
- JSON encoding for complex fields
- Preserves all test case information
- Includes metadata as comments

## 🏗️ Architecture

APIForge follows a modular, enterprise-grade architecture:

### 📊 System Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  📄 SpecLoader  │────▶│  📋 SpecParser  │────▶│  🤖 Generator   │
│  (Async HTTP)   │     │(Pydantic Models)│     │ (LLM Provider)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 ▼
                  ┌──────────────────────────────┐
                  │     🎭 Orchestrator          │
                  │  (Workflow Coordination)     │
                  │    + Task Scheduling         │
                  └──────────────────────────────┘
                     │            │            │
                     ▼            ▼            ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │💾 SQLite │ │📊 Web UI │ │📁 Output │
              │  Queue   │ │ Monitor  │ │ JSON/CSV │
              └──────────┘ └──────────┘ └──────────┘
```

### 🔄 Data Flow Sequence

```
User Input                  Processing                    Output
    │                           │                           │
    ▼                           ▼                           ▼
🌐 API URL ──▶ 📥 Load Spec ──▶ 🔍 Parse ──▶ 🧠 Generate ──▶ 💾 Save
                    │               │              │
                    └───────────────┴──────────────┘
                                    │
                              📊 Monitor Progress
```

### 🧩 Core Components

- **📄 SpecLoader**: Async HTTP client for loading OpenAPI specifications
- **📋 SpecParser**: Pydantic-based parser for extracting endpoint information
- **🤖 Generator**: Test case generation with LLM provider abstraction
- **🎭 Orchestrator**: Workflow coordination with concurrent processing
- **⚡ Task Scheduler**: SQLite-based task queue with retry logic
- **📊 Web UI**: FastAPI-based dashboard with real-time monitoring
- **🔌 Providers**: Pluggable LLM provider system (OpenAI, Qwen, Custom)

### 📈 Performance & Scalability

```
┌─────────────────────────────────────────────────────────┐
│              Execution Mode Comparison                  │
├─────────────┬────────────────┬─────────────────────────┤
│    Mode     │  Concurrency   │      Performance        │
├─────────────┼────────────────┼─────────────────────────┤
│ 🚀 Fast     │ Max (10-50)    │ 100+ endpoints/min      │
│ 🎯 Smart    │ Dynamic (5-20) │ 50-80 endpoints/min     │
│ 📊 Auto     │ Progressive    │ 30-60 endpoints/min     │
│ 🧠 AI       │ Limited (1-5)  │ 10-20 endpoints/min     │
└─────────────┴────────────────┴─────────────────────────┘
```

## 🔧 Development

### 🔨 Setup Development Environment

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run code formatting
black apiforge/
isort apiforge/

# Run type checking
mypy apiforge/

# Run linting
flake8 apiforge/
```

### 🤖 Adding New LLM Providers

1. Create a new provider class inheriting from `LLMProvider`:

```python
from apiforge.providers.base import LLMProvider

class CustomProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "Custom"
    
    async def generate_test_cases_async(self, endpoint: EndpointInfo) -> List[Dict]:
        # Implementation here
        pass
```

2. Register the provider:

```python
from apiforge.generator import TestCaseGenerator

TestCaseGenerator.register_provider("custom", CustomProvider)
```

### 🚀 Running Examples

```bash
# Set up environment
cp .env.example .env
# Edit .env with your API key

# Run Petstore example
cd examples
python generate_petstore_tests.py
```

## 🛡️ Security

- **API Key Management**: Never hardcode API keys; use environment variables
- **Input Validation**: Comprehensive validation of OpenAPI specifications
- **Output Sanitization**: Automatic sanitization of sensitive information in logs
- **Secure Defaults**: Security-first configuration defaults

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### 🔄 Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass and code is formatted
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [Pydantic](https://pydantic.dev/) for data validation
- Uses [httpx](https://www.python-httpx.org/) for async HTTP requests
- CLI powered by [Click](https://click.palletsprojects.com/) and [Rich](https://rich.readthedocs.io/)
- OpenAI integration via the official [OpenAI Python SDK](https://github.com/openai/openai-python)

## 📞 Support

- **Documentation**: See `/docs` directory for detailed documentation
- **CSV Format**: See `/docs/csv_format_design.md` for CSV format specification
- **Issues**: [GitHub Issues](https://github.com/your-org/apiforge/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/apiforge/discussions)

---

**APIForge** - Forging intelligent API tests with AI-powered automation 🚀

---

## 中文

## 🌟 功能特性

- **自动化测试用例生成**：从 OpenAPI/Swagger 规范自动生成全面的测试用例
- **多 LLM 提供商支持**：支持 OpenAI、自定义 API 和千问（带 /no_think 优化，速度提升 10 倍）
- **企业级架构**：
  - 异步优先设计，具有强大的错误处理和重试逻辑
  - 基于 SQLite 的持久化任务队列
  - 优雅的关闭和任务恢复机制
- **高级测试设计方法**：
  - 边界值分析（BVA）- 测试边缘情况和极限值
  - 决策表 - 覆盖所有逻辑组合
  - 状态转换 - 测试 API 状态变化
  - 成对测试 - 优化测试组合
  - 等价类划分 - 分组相似测试场景
- **增强的测试覆盖率**：每个端点使用多种测试策略生成 5-20 个测试用例
- **智能任务调度**：
  - 基于 SQLite 的持久化任务队列
  - 基于负载的动态工作器扩展
  - 带 API 模式匹配的渐进式调度
  - 实时优化的混合调度
- **Web 监控仪表板**：
  - 基于 WebSocket 的实时进度跟踪
  - 会话管理和历史记录
  - 任务重试和错误跟踪
  - 性能指标和统计数据
  - 导出报告（CSV/JSON）
- **多种输出格式**：
  - 标准化架构的 JSON
  - 适用于电子表格工具和测试管理系统的 CSV
  - 用于调试的中间文件
- **生产就绪特性**：
  - 强大的错误处理和自动重试
  - 速率限制和并发控制
  - 大型 API 的内存高效处理
  - 优雅关闭和任务持久化
- **可扩展的提供商系统**：轻松添加对新 LLM 提供商的支持
- **安全优先**：安全处理 API 密钥和敏感信息
- **丰富的 CLI 界面**：带有进度指示器的美观命令行界面

## 🚀 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/apiforge/apiforge.git
cd apiforge

# 安装依赖
pip install -e .
```

### 配置

1. 复制环境模板：
```bash
cp .env.example .env
```

2. 配置您喜欢的 LLM 提供商：

**使用千问（默认 - 快速且免费）：**
```bash
LLM_PROVIDER=qwen
# 无需 API 密钥，使用默认端点
```

**使用 OpenAI：**
```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-api-key-here
```

### 基本用法

从 OpenAPI 规范生成测试用例：

```bash
# 基本用法（使用默认千问提供商）
python run.py --url https://petstore.swagger.io/v2/swagger.json --output petstore_tests.json

# 生成 CSV 格式的测试用例
python run.py --url https://petstore.swagger.io/v2/swagger.json --output petstore_tests.csv

# 使用不同的执行模式
python run.py --url https://api.example.com/spec.json --output tests.json --mode auto
# 可用模式：auto（智能渐进式）、fast（最大并发）、
#          smart（动态调度）、ai-analysis（AI 驱动的深度分析）
```

### 监控仪表板

APIForge 包含强大的监控仪表板，用于跟踪测试生成进度：

```bash
# 启动独立监控仪表板
python run.py dashboard

# 或运行生成并自动监控
python run.py --url https://api.example.com/spec.json --output tests.json --monitor
```

访问仪表板：
- **主仪表板**：http://localhost:9099
- **实时监控**：http://localhost:9099/monitor
- **错误日志**：http://localhost:9099/errors
- **统计数据**：http://localhost:9099/statistics

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

**APIForge** - 用 AI 驱动的自动化锻造智能 API 测试 🚀