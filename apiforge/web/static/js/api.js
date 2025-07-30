// API服务封装层
class APIService {
  constructor() {
    this.baseURL = window.location.origin;
    this.defaultHeaders = {
      'Content-Type': 'application/json'
    };
  }

  // 通用请求方法
  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    const config = {
      ...options,
      headers: {
        ...this.defaultHeaders,
        ...options.headers
      }
    };

    try {
      const response = await fetch(url, config);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      // 处理空响应
      const text = await response.text();
      return text ? JSON.parse(text) : null;
    } catch (error) {
      console.error(`API Error: ${endpoint}`, error);
      throw error;
    }
  }

  // GET 请求
  async get(endpoint, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const url = queryString ? `${endpoint}?${queryString}` : endpoint;
    return this.request(url, { method: 'GET' });
  }

  // POST 请求
  async post(endpoint, data = {}) {
    return this.request(endpoint, {
      method: 'POST',
      body: JSON.stringify(data)
    });
  }

  // 项目相关 API
  async getProjects() {
    return this.get('/api/projects');
  }

  async getProjectProgress(projectId) {
    return this.get(`/api/project/${projectId}/progress`);
  }

  // 任务相关 API
  async getRecentTasks(params = {}) {
    return this.get('/api/tasks/recent', params);
  }

  async getTaskDetail(taskId) {
    return this.get(`/api/task/${taskId}`);
  }

  async retryTask(taskId) {
    return this.post(`/api/task/${taskId}/retry`);
  }

  async cancelTask(taskId) {
    return this.post(`/api/task/${taskId}/cancel`);
  }

  async exportTaskTestCases(taskId) {
    const response = await fetch(`${this.baseURL}/api/task/${taskId}/test-cases/export`);
    if (!response.ok) {
      throw new Error(`Export failed: ${response.status}`);
    }
    return response.blob();
  }

  // 统计相关 API
  async getHourlyStatistics(params = {}) {
    return this.get('/api/statistics/hourly', params);
  }

  async getPerformanceStatistics(params = {}) {
    return this.get('/api/statistics/performance', params);
  }

  async exportStatistics(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const url = `/api/statistics/export?${queryString}`;
    const response = await fetch(`${this.baseURL}${url}`);
    if (!response.ok) {
      throw new Error(`Export failed: ${response.status}`);
    }
    return response.blob();
  }

  // 错误日志 API
  async getErrorLogs(params = {}) {
    return this.get('/api/errors', params);
  }

  // 系统健康 API
  async getHealthStatus() {
    return this.get('/api/health');
  }

  // Worker管理 API
  async getWorkersStatus() {
    return this.get('/api/workers');
  }

  async cleanupOfflineWorkers() {
    return this.post('/api/workers/cleanup');
  }

  // 导出任务数据
  async exportTasks(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const url = `/api/export/tasks?${queryString}`;
    const response = await fetch(`${this.baseURL}${url}`);
    if (!response.ok) {
      throw new Error(`Export failed: ${response.status}`);
    }
    return response.blob();
  }

  // 导出统计报告
  async exportStatisticsReport(params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const url = `/api/export/statistics?${queryString}`;
    const response = await fetch(`${this.baseURL}${url}`);
    if (!response.ok) {
      throw new Error(`Export failed: ${response.status}`);
    }
    return response.blob();
  }

  // 下载文件辅助方法
  downloadFile(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  }
}

// 创建全局 API 实例
window.api = new APIService();