// Complete utils implementation
window.utils = {
  // DOM helper functions
  createElement: function(tag, options) {
    var element = document.createElement(tag);
    if (options) {
      if (options.className) element.className = options.className;
      if (options.textContent) element.textContent = options.textContent;
      if (options.innerHTML) element.innerHTML = options.innerHTML;
      if (options.onclick) element.onclick = options.onclick;
    }
    return element;
  },
  
  showEmptyState: function(container, message) {
    container.innerHTML = '<div class="text-center text-muted p-4">' + message + '</div>';
  },
  
  formatRelativeTime: function(dateString) {
    if (!dateString) return '-';
    var date = new Date(dateString);
    var now = new Date();
    var diffMs = now - date;
    var diffMinutes = Math.floor(diffMs / (1000 * 60));
    
    if (diffMinutes < 1) return '刚刚';
    if (diffMinutes < 60) return diffMinutes + '分钟前';
    
    var diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return diffHours + '小时前';
    
    var diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return diffDays + '天前';
    
    return this.formatDateTime(dateString);
  },
  formatDateTime: function(dateString) {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleString('zh-CN');
  },
  
  formatNumber: function(num) {
    if (num === null || num === undefined) return '-';
    return num.toLocaleString();
  },
  
  formatPercentage: function(value, decimals) {
    if (value === null || value === undefined) return '-';
    decimals = decimals || 1;
    return value.toFixed(decimals) + '%';
  },
  
  formatPercent: function(value, decimals) {
    // Alias for formatPercentage
    return this.formatPercentage(value, decimals);
  },
  
  parseQueryParams: function(url) {
    var params = {};
    var queryString = url || window.location.search;
    if (queryString.indexOf('?') > -1) {
      queryString = queryString.split('?')[1];
    }
    if (queryString) {
      var pairs = queryString.split('&');
      for (var i = 0; i < pairs.length; i++) {
        var pair = pairs[i].split('=');
        if (pair[0]) {
          params[decodeURIComponent(pair[0])] = pair[1] ? decodeURIComponent(pair[1]) : '';
        }
      }
    }
    return params;
  },
  
  updateQueryParams: function(params) {
    var currentParams = this.parseQueryParams();
    // Merge new params with existing ones
    for (var key in params) {
      if (params.hasOwnProperty(key)) {
        currentParams[key] = params[key];
      }
    }
    // Build new query string
    var pairs = [];
    for (var key in currentParams) {
      if (currentParams.hasOwnProperty(key) && currentParams[key] !== null && currentParams[key] !== undefined) {
        pairs.push(encodeURIComponent(key) + '=' + encodeURIComponent(currentParams[key]));
      }
    }
    var newQueryString = pairs.length > 0 ? '?' + pairs.join('&') : '';
    // Update URL without reload
    if (window.history && window.history.replaceState) {
      var newUrl = window.location.pathname + newQueryString + window.location.hash;
      window.history.replaceState(null, '', newUrl);
    }
  },
  
  getStatusClass: function(status) {
    var statusMap = {
      'completed': 'status-success',
      'failed': 'status-error',
      'pending': 'status-warning',
      'in_progress': 'status-info',
      'active': 'status-info'
    };
    return statusMap[status] || 'status-muted';
  },
  
  getStatusText: function(status) {
    var statusMap = {
      'completed': '已完成',
      'failed': '失败',
      'pending': '等待中',
      'in_progress': '进行中',
      'active': '活跃中'
    };
    return statusMap[status] || status;
  },
  
  getBadgeClass: function(status) {
    var classMap = {
      'completed': 'badge-success',
      'failed': 'badge-error',
      'pending': 'badge-warning',
      'in_progress': 'badge-info',
      'active': 'badge-primary',
      'cancelled': 'badge-muted'
    };
    return classMap[status] || 'badge-muted';
  },
  
  createAutoRefresh: function(callback, interval) {
    var timerId = null;
    var isRunning = false;
    interval = interval || 5000;
    
    return {
      start: function() {
        if (isRunning) return;
        isRunning = true;
        timerId = setInterval(callback, interval);
      },
      stop: function() {
        if (!isRunning) return;
        isRunning = false;
        if (timerId) {
          clearInterval(timerId);
          timerId = null;
        }
      },
      isRunning: function() {
        return isRunning;
      }
    };
  },
  
  formatDuration: function(seconds) {
    if (seconds === null || seconds === undefined || seconds === 0) return '-';
    if (seconds < 1) return (seconds * 1000).toFixed(0) + 'ms';
    if (seconds < 60) return seconds.toFixed(1) + 's';
    
    var minutes = Math.floor(seconds / 60);
    var remainingSeconds = seconds % 60;
    if (minutes < 60) {
      return minutes + 'm ' + remainingSeconds.toFixed(0) + 's';
    }
    
    var hours = Math.floor(minutes / 60);
    var remainingMinutes = minutes % 60;
    return hours + 'h ' + remainingMinutes + 'm';
  },
  
  showError: function(container, message) {
    container.innerHTML = '<div class="text-center text-danger p-4"><i class="fas fa-exclamation-triangle"></i> ' + message + '</div>';
  }
};