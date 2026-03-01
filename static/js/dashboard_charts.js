/**
 * dashboard_charts.js
 * ═════════════════════════════════════════════════════════════════════
 * Dashboard charts using Chart.js
 * 
 * Features:
 * - Grade distribution chart (donut/pie)
 * - Assignment completion chart (bar)
 * - Student progress chart (line)
 * - Reusable chart initialization
 * 
 * Requirements:
 * - Chart.js library (include via CDN or npm)
 * 
 * Usage:
 *   DashboardCharts.initGradeDistribution('chartId', data);
 *   DashboardCharts.initCompletionChart('chartId', data);
 *   DashboardCharts.initProgressChart('chartId', data);
 */

const DashboardCharts = (function() {
    'use strict';

    // Chart.js default configuration
    const defaultOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'bottom',
                labels: {
                    padding: 15,
                    font: {
                        size: 12,
                        family: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
                    }
                }
            },
            tooltip: {
                backgroundColor: 'rgba(0, 0, 0, 0.8)',
                padding: 12,
                titleFont: {
                    size: 14
                },
                bodyFont: {
                    size: 13
                },
                cornerRadius: 6
            }
        }
    };

    // Color schemes
    const colorSchemes = {
        blue: ['#3b82f6', '#60a5fa', '#93c5fd', '#bfdbfe', '#dbeafe'],
        green: ['#10b981', '#34d399', '#6ee7b7', '#a7f3d0', '#d1fae5'],
        mixed: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
        gradient: ['#2563eb', '#3b82f6', '#60a5fa', '#93c5fd', '#bfdbfe']
    };

    /**
     * Initialize Grade Distribution Chart (Donut/Pie)
     * @param {string} canvasId - Canvas element ID
     * @param {object} data - Chart data {labels: [], values: []}
     * @param {object} options - Additional options
     */
    function initGradeDistribution(canvasId, data, options = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas element #${canvasId} not found`);
            return null;
        }

        const ctx = canvas.getContext('2d');
        
        // Destroy existing chart if any
        if (canvas.chart) {
            canvas.chart.destroy();
        }

        const chartData = {
            labels: data.labels || ['A (90-100)', 'B (80-89)', 'C (70-79)', 'D (60-69)', 'F (<60)'],
            datasets: [{
                label: 'Qiymət Paylanması',
                data: data.values || [0, 0, 0, 0, 0],
                backgroundColor: options.colors || colorSchemes.mixed,
                borderColor: '#ffffff',
                borderWidth: 2,
                hoverOffset: 10
            }]
        };

        const chartOptions = {
            ...defaultOptions,
            plugins: {
                ...defaultOptions.plugins,
                title: {
                    display: options.showTitle !== false,
                    text: options.title || 'Qiymət Paylanması',
                    font: {
                        size: 16,
                        weight: 'bold'
                    },
                    padding: {
                        top: 10,
                        bottom: 20
                    }
                },
                tooltip: {
                    ...defaultOptions.plugins.tooltip,
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                            return `${label}: ${value} tələbə (${percentage}%)`;
                        }
                    }
                }
            }
        };

        canvas.chart = new Chart(ctx, {
            type: options.type || 'doughnut',
            data: chartData,
            options: chartOptions
        });

        return canvas.chart;
    }

    /**
     * Initialize Assignment Completion Chart (Bar)
     * @param {string} canvasId - Canvas element ID
     * @param {object} data - Chart data {labels: [], completed: [], pending: []}
     * @param {object} options - Additional options
     */
    function initCompletionChart(canvasId, data, options = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas element #${canvasId} not found`);
            return null;
        }

        const ctx = canvas.getContext('2d');
        
        // Destroy existing chart if any
        if (canvas.chart) {
            canvas.chart.destroy();
        }

        const chartData = {
            labels: data.labels || [],
            datasets: [
                {
                    label: 'Tamamlanmış',
                    data: data.completed || [],
                    backgroundColor: '#10b981',
                    borderColor: '#059669',
                    borderWidth: 1,
                    borderRadius: 5,
                    borderSkipped: false
                },
                {
                    label: 'Gözləyən',
                    data: data.pending || [],
                    backgroundColor: '#f59e0b',
                    borderColor: '#d97706',
                    borderWidth: 1,
                    borderRadius: 5,
                    borderSkipped: false
                }
            ]
        };

        const chartOptions = {
            ...defaultOptions,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1,
                        font: {
                            size: 11
                        }
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                },
                x: {
                    ticks: {
                        font: {
                            size: 11
                        }
                    },
                    grid: {
                        display: false
                    }
                }
            },
            plugins: {
                ...defaultOptions.plugins,
                title: {
                    display: options.showTitle !== false,
                    text: options.title || 'Tapşırıq Tamamlanması',
                    font: {
                        size: 16,
                        weight: 'bold'
                    },
                    padding: {
                        top: 10,
                        bottom: 20
                    }
                },
                tooltip: {
                    ...defaultOptions.plugins.tooltip,
                    callbacks: {
                        label: function(context) {
                            const label = context.dataset.label || '';
                            const value = context.parsed.y || 0;
                            return `${label}: ${value} tələbə`;
                        }
                    }
                }
            }
        };

        canvas.chart = new Chart(ctx, {
            type: 'bar',
            data: chartData,
            options: chartOptions
        });

        return canvas.chart;
    }

    /**
     * Initialize Student Progress Chart (Line)
     * @param {string} canvasId - Canvas element ID
     * @param {object} data - Chart data {labels: [], datasets: [{label, data}]}
     * @param {object} options - Additional options
     */
    function initProgressChart(canvasId, data, options = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas element #${canvasId} not found`);
            return null;
        }

        const ctx = canvas.getContext('2d');
        
        // Destroy existing chart if any
        if (canvas.chart) {
            canvas.chart.destroy();
        }

        // Process datasets
        const datasets = (data.datasets || []).map((dataset, index) => ({
            label: dataset.label,
            data: dataset.data,
            borderColor: colorSchemes.gradient[index % colorSchemes.gradient.length],
            backgroundColor: `${colorSchemes.gradient[index % colorSchemes.gradient.length]}20`,
            tension: 0.4,
            fill: options.fill !== false,
            pointRadius: 4,
            pointHoverRadius: 6,
            pointBackgroundColor: '#ffffff',
            pointBorderWidth: 2,
            borderWidth: 2
        }));

        const chartData = {
            labels: data.labels || [],
            datasets: datasets
        };

        const chartOptions = {
            ...defaultOptions,
            scales: {
                y: {
                    beginAtZero: true,
                    max: options.maxScore || 100,
                    ticks: {
                        font: {
                            size: 11
                        },
                        callback: function(value) {
                            return value + (options.unit || '');
                        }
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                },
                x: {
                    ticks: {
                        font: {
                            size: 11
                        }
                    },
                    grid: {
                        display: false
                    }
                }
            },
            plugins: {
                ...defaultOptions.plugins,
                title: {
                    display: options.showTitle !== false,
                    text: options.title || 'Tələbə Proqressi',
                    font: {
                        size: 16,
                        weight: 'bold'
                    },
                    padding: {
                        top: 10,
                        bottom: 20
                    }
                },
                tooltip: {
                    ...defaultOptions.plugins.tooltip,
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function(context) {
                            const label = context.dataset.label || '';
                            const value = context.parsed.y || 0;
                            return `${label}: ${value}${options.unit || ''}`;
                        }
                    }
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            }
        };

        canvas.chart = new Chart(ctx, {
            type: 'line',
            data: chartData,
            options: chartOptions
        });

        return canvas.chart;
    }

    /**
     * Initialize a simple bar chart
     * @param {string} canvasId - Canvas element ID
     * @param {object} data - Chart data {labels: [], values: []}
     * @param {object} options - Additional options
     */
    function initBarChart(canvasId, data, options = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas element #${canvasId} not found`);
            return null;
        }

        const ctx = canvas.getContext('2d');
        
        if (canvas.chart) {
            canvas.chart.destroy();
        }

        const chartData = {
            labels: data.labels || [],
            datasets: [{
                label: options.label || 'Dəyər',
                data: data.values || [],
                backgroundColor: options.colors || colorSchemes.blue,
                borderColor: options.borderColors || colorSchemes.gradient,
                borderWidth: 1,
                borderRadius: 5,
                borderSkipped: false
            }]
        };

        const chartOptions = {
            ...defaultOptions,
            indexAxis: options.horizontal ? 'y' : 'x',
            scales: {
                [options.horizontal ? 'x' : 'y']: {
                    beginAtZero: true,
                    ticks: {
                        font: { size: 11 }
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                },
                [options.horizontal ? 'y' : 'x']: {
                    ticks: {
                        font: { size: 11 }
                    },
                    grid: {
                        display: false
                    }
                }
            },
            plugins: {
                ...defaultOptions.plugins,
                title: {
                    display: options.showTitle !== false,
                    text: options.title || '',
                    font: {
                        size: 16,
                        weight: 'bold'
                    },
                    padding: {
                        top: 10,
                        bottom: 20
                    }
                }
            }
        };

        canvas.chart = new Chart(ctx, {
            type: 'bar',
            data: chartData,
            options: chartOptions
        });

        return canvas.chart;
    }

    /**
     * Initialize a radar chart
     * @param {string} canvasId - Canvas element ID
     * @param {object} data - Chart data {labels: [], datasets: [{label, data}]}
     * @param {object} options - Additional options
     */
    function initRadarChart(canvasId, data, options = {}) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas element #${canvasId} not found`);
            return null;
        }

        const ctx = canvas.getContext('2d');
        
        if (canvas.chart) {
            canvas.chart.destroy();
        }

        const datasets = (data.datasets || []).map((dataset, index) => ({
            label: dataset.label,
            data: dataset.data,
            backgroundColor: `${colorSchemes.gradient[index % colorSchemes.gradient.length]}20`,
            borderColor: colorSchemes.gradient[index % colorSchemes.gradient.length],
            pointBackgroundColor: colorSchemes.gradient[index % colorSchemes.gradient.length],
            pointBorderColor: '#fff',
            pointHoverBackgroundColor: '#fff',
            pointHoverBorderColor: colorSchemes.gradient[index % colorSchemes.gradient.length]
        }));

        const chartData = {
            labels: data.labels || [],
            datasets: datasets
        };

        const chartOptions = {
            ...defaultOptions,
            scales: {
                r: {
                    beginAtZero: true,
                    max: options.maxScore || 100,
                    ticks: {
                        font: { size: 10 }
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.1)'
                    }
                }
            },
            plugins: {
                ...defaultOptions.plugins,
                title: {
                    display: options.showTitle !== false,
                    text: options.title || '',
                    font: {
                        size: 16,
                        weight: 'bold'
                    },
                    padding: {
                        top: 10,
                        bottom: 20
                    }
                }
            }
        };

        canvas.chart = new Chart(ctx, {
            type: 'radar',
            data: chartData,
            options: chartOptions
        });

        return canvas.chart;
    }

    /**
     * Update chart data dynamically
     * @param {Chart} chart - Chart instance
     * @param {object} newData - New data
     */
    function updateChart(chart, newData) {
        if (!chart) {
            console.error('Chart instance not found');
            return;
        }

        if (newData.labels) {
            chart.data.labels = newData.labels;
        }

        if (newData.datasets) {
            newData.datasets.forEach((dataset, index) => {
                if (chart.data.datasets[index]) {
                    chart.data.datasets[index].data = dataset.data;
                }
            });
        } else if (newData.values) {
            chart.data.datasets[0].data = newData.values;
        }

        chart.update('active');
    }

    /**
     * Destroy chart
     * @param {string} canvasId - Canvas element ID
     */
    function destroyChart(canvasId) {
        const canvas = document.getElementById(canvasId);
        if (canvas && canvas.chart) {
            canvas.chart.destroy();
            canvas.chart = null;
        }
    }

    // Public API
    return {
        initGradeDistribution,
        initCompletionChart,
        initProgressChart,
        initBarChart,
        initRadarChart,
        updateChart,
        destroyChart,
        colorSchemes
    };
})();

// Check if Chart.js is loaded
if (typeof Chart === 'undefined') {
    console.warn('Chart.js is not loaded. Please include Chart.js library before dashboard_charts.js');
    console.info('Add this to your HTML: <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>');
}

// Example usage (can be removed in production)
/*
document.addEventListener('DOMContentLoaded', function() {
    // Grade Distribution Example
    if (document.getElementById('gradeChart')) {
        DashboardCharts.initGradeDistribution('gradeChart', {
            labels: ['A (90-100)', 'B (80-89)', 'C (70-79)', 'D (60-69)', 'F (<60)'],
            values: [15, 25, 30, 20, 10]
        });
    }

    // Assignment Completion Example
    if (document.getElementById('completionChart')) {
        DashboardCharts.initCompletionChart('completionChart', {
            labels: ['Tapşırıq 1', 'Tapşırıq 2', 'Tapşırıq 3', 'Tapşırıq 4'],
            completed: [45, 38, 42, 35],
            pending: [5, 12, 8, 15]
        });
    }

    // Student Progress Example
    if (document.getElementById('progressChart')) {
        DashboardCharts.initProgressChart('progressChart', {
            labels: ['Həftə 1', 'Həftə 2', 'Həftə 3', 'Həftə 4', 'Həftə 5'],
            datasets: [
                {
                    label: 'Orta bal',
                    data: [65, 72, 78, 85, 88]
                }
            ]
        }, { maxScore: 100 });
    }
});
*/
