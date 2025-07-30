// 图表配置和工具函数
const chartUtils = {
  // 默认颜色方案
  colors: {
    primary: '#2563eb',
    success: '#10b981',
    warning: '#f59e0b',
    danger: '#ef4444',
    info: '#3b82f6',
    gray: '#6b7280'
  },

  // 图表默认配置
  defaultOptions: {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
        labels: {
          boxWidth: 12,
          padding: 10,
          font: {
            size: 12
          }
        }
      },
      tooltip: {
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        padding: 10,
        cornerRadius: 4,
        titleFont: {
          size: 12
        },
        bodyFont: {
          size: 12
        }
      }
    },
    scales: {
      x: {
        grid: {
          display: false
        },
        ticks: {
          font: {
            size: 11
          }
        }
      },
      y: {
        beginAtZero: true,
        grid: {
          color: 'rgba(0, 0, 0, 0.05)'
        },
        ticks: {
          font: {
            size: 11
          }
        }
      }
    }
  },

  // 创建性能分布饼图
  createPerformanceChart(ctx, data) {
    return new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: data.labels,
        datasets: [{
          data: data.values,
          backgroundColor: [
            this.colors.success,
            this.colors.warning,
            this.colors.danger,
            this.colors.info,
            this.colors.gray
          ],
          borderWidth: 0
        }]
      },
      options: {
        ...this.defaultOptions,
        cutout: '60%',
        plugins: {
          ...this.defaultOptions.plugins,
          legend: {
            position: 'right',
            labels: {
              padding: 15,
              font: {
                size: 12
              }
            }
          }
        }
      }
    });
  },

  // 创建时间线图表
  createTimelineChart(ctx, data) {
    return new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.labels,
        datasets: [{
          label: '完成任务',
          data: data.completed,
          borderColor: this.colors.success,
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          tension: 0.3,
          fill: true
        }, {
          label: '失败任务',
          data: data.failed,
          borderColor: this.colors.danger,
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          tension: 0.3,
          fill: true
        }]
      },
      options: {
        ...this.defaultOptions,
        interaction: {
          intersect: false,
          mode: 'index'
        },
        scales: {
          ...this.defaultOptions.scales,
          y: {
            ...this.defaultOptions.scales.y,
            stacked: false
          }
        }
      }
    });
  },

  // 创建状态分布图
  createStatusChart(ctx, data) {
    return new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ['完成', '失败', '进行中', '待处理'],
        datasets: [{
          label: '任务数量',
          data: [
            data.completed || 0,
            data.failed || 0,
            data.in_progress || 0,
            data.pending || 0
          ],
          backgroundColor: [
            this.colors.success,
            this.colors.danger,
            this.colors.info,
            this.colors.warning
          ]
        }]
      },
      options: {
        ...this.defaultOptions,
        plugins: {
          ...this.defaultOptions.plugins,
          legend: {
            display: false
          }
        }
      }
    });
  },

  // 创建响应时间分布图
  createResponseTimeChart(ctx, data) {
    return new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.map(item => item.bucket),
        datasets: [{
          label: '任务数量',
          data: data.map(item => item.count),
          backgroundColor: this.colors.primary,
          borderRadius: 4
        }]
      },
      options: {
        ...this.defaultOptions,
        plugins: {
          ...this.defaultOptions.plugins,
          legend: {
            display: false
          }
        },
        scales: {
          ...this.defaultOptions.scales,
          y: {
            ...this.defaultOptions.scales.y,
            title: {
              display: true,
              text: '任务数量',
              font: {
                size: 12
              }
            }
          },
          x: {
            ...this.defaultOptions.scales.x,
            title: {
              display: true,
              text: '响应时间',
              font: {
                size: 12
              }
            }
          }
        }
      }
    });
  },

  // 创建重试成功率图表
  createRetryChart(ctx, data) {
    const labels = data.map(item => `重试 ${item.retry_count} 次`);
    const successRates = data.map(item => item.success_rate);
    
    return new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: '成功率 (%)',
          data: successRates,
          borderColor: this.colors.primary,
          backgroundColor: 'rgba(37, 99, 235, 0.1)',
          tension: 0.3,
          fill: true,
          pointStyle: 'circle',
          pointRadius: 5,
          pointHoverRadius: 7
        }]
      },
      options: {
        ...this.defaultOptions,
        scales: {
          ...this.defaultOptions.scales,
          y: {
            ...this.defaultOptions.scales.y,
            max: 100,
            ticks: {
              callback: function(value) {
                return value + '%';
              }
            }
          }
        },
        plugins: {
          ...this.defaultOptions.plugins,
          tooltip: {
            ...this.defaultOptions.plugins.tooltip,
            callbacks: {
              label: function(context) {
                return context.dataset.label + ': ' + context.parsed.y.toFixed(1) + '%';
              }
            }
          }
        }
      }
    });
  },

  // 更新图表数据
  updateChartData(chart, newData) {
    if (!chart) return;
    
    chart.data = newData;
    chart.update();
  },

  // 销毁图表
  destroyChart(chart) {
    if (chart) {
      chart.destroy();
    }
  },

  // 格式化图表数据
  formatHourlyData(data) {
    const labels = data.map(d => {
      const date = new Date(d.time);
      return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:00`;
    });
    
    const completed = data.map(d => d.completed || 0);
    const failed = data.map(d => d.failed || 0);
    const total = data.map(d => d.total || 0);
    
    return {
      labels,
      completed,
      failed,
      total
    };
  },

  // 导出图表为图片
  exportChartAsImage(chart, filename = 'chart.png') {
    if (!chart) return;
    
    const url = chart.toBase64Image();
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
  }
};

// 导出工具
window.chartUtils = chartUtils;