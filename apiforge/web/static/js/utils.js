// 工具函数
const utils = {
  // 格式化时间
  formatDateTime(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
  },

  // 相对时间
  formatRelativeTime(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    
    if (diffMinutes < 1) return '刚刚';
    if (diffMinutes < 60) return `${diffMinutes}分钟前`;
    
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours}小时前`;
    
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}天前`;
    
    return this.formatDateTime(dateString);
  },

  // 格式化数字
  formatNumber(num) {
    if (num === null || num === undefined) return '-';
    return num.toLocaleString();
  },

  // 格式化百分比
  formatPercentage(value, decimals = 1) {
    if (value === null || value === undefined) return '-';
    return `${value.toFixed(decimals)}%`;
  },

  // 格式化文件大小
  formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  },

  // 获取状态显示类
  getStatusClass(status) {
    const statusMap = {
      'completed': 'status-success',
      'failed': 'status-error', 
      'pending': 'status-warning',
      'in_progress': 'status-info',
      'cancelled': 'status-muted',
      'active': 'status-info'
    };
    return statusMap[status] || 'status-muted';
  },

  // 获取状态显示文本
  getStatusText(status) {
    const statusMap = {
      'completed': '已完成',
      'failed': '失败',
      'pending': '等待中',
      'in_progress': '进行中',
      'cancelled': '已取消',
      'active': '活跃中'
    };
    return statusMap[status] || status;
  },

  // 创建自动刷新器
  createAutoRefresh(callback, interval = 5000) {
    let timerId = null;
    let isRunning = false;
    
    return {
      start() {
        if (isRunning) return;
        isRunning = true;
        timerId = setInterval(callback, interval);
      },
      
      stop() {
        if (!isRunning) return;
        isRunning = false;
        if (timerId) {
          clearInterval(timerId);
          timerId = null;
        }
      },
      
      isRunning() {
        return isRunning;
      }
    };
  },

  // 防抖函数
  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  },

  // 节流函数
  throttle(func, limit) {
    let inThrottle;
    return function() {
      const args = arguments;
      const context = this;
      if (!inThrottle) {
        func.apply(context, args);
        inThrottle = true;
        setTimeout(() => inThrottle = false, limit);
      }
    };
  },

  // 错误处理
  handleError(error, context = '') {
    console.error(`Error in ${context}:`, error);
    
    // 显示用户友好的错误信息
    let message = '操作失败，请稍后重试';
    if (error.message) {
      if (error.message.includes('fetch')) {
        message = '网络连接失败，请检查网络';
      } else if (error.message.includes('JSON')) {
        message = '数据格式错误';
      }
    }
    
    this.showNotification(message, 'error');
  },

  // 显示通知
  showNotification(message, type = 'info', duration = 3000) {
    // 创建通知元素
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    // 添加到页面
    document.body.appendChild(notification);
    
    // 自动移除
    setTimeout(() => {
      if (notification.parentNode) {
        notification.parentNode.removeChild(notification);
      }
    }, duration);
  },

  // 复制到剪贴板
  async copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text);
      this.showNotification('已复制到剪贴板', 'success');
    } catch (err) {
      console.error('复制失败:', err);
      this.showNotification('复制失败', 'error');
    }
  },

  // 下载文件
  downloadFile(data, filename, type = 'application/json') {
    const blob = new Blob([data], { type });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  },

  // 生成UUID
  generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0;
      const v = c == 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }
};