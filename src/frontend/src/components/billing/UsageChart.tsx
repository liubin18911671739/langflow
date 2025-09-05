import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Progress } from '../ui/progress';

interface UsageMetric {
  name: string;
  value: number;
  limit: number;
  percentage: number;
  unit: string;
}

interface UsageChartProps {
  metrics: UsageMetric[];
  title?: string;
}

const UsageChart: React.FC<UsageChartProps> = ({ 
  metrics, 
  title = "Usage Overview" 
}) => {
  const formatValue = (value: number, unit: string) => {
    if (unit === 'mb') {
      if (value >= 1024) {
        return `${(value / 1024).toFixed(1)} GB`;
      }
      return `${value} MB`;
    }
    if (value >= 1000000) {
      return `${(value / 1000000).toFixed(1)}M`;
    }
    if (value >= 1000) {
      return `${(value / 1000).toFixed(1)}K`;
    }
    return value.toString();
  };

  const getStatusColor = (percentage: number) => {
    if (percentage >= 90) return 'text-red-600';
    if (percentage >= 70) return 'text-yellow-600';
    return 'text-green-600';
  };

  const getProgressColor = (percentage: number) => {
    if (percentage >= 90) return 'bg-red-500';
    if (percentage >= 70) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  const chartData = metrics.map(metric => ({
    name: metric.name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
    used: metric.value,
    limit: metric.limit === -1 ? 0 : metric.limit,
    percentage: metric.percentage,
    unlimited: metric.limit === -1
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {/* Usage Progress Bars */}
          <div className="grid gap-4">
            {metrics.map((metric, index) => (
              <div key={index} className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">
                    {metric.name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className={getStatusColor(metric.percentage)}>
                      {formatValue(metric.value, metric.unit)}
                    </span>
                    {metric.limit !== -1 && (
                      <>
                        <span className="text-muted-foreground">/</span>
                        <span className="text-muted-foreground">
                          {formatValue(metric.limit, metric.unit)}
                        </span>
                      </>
                    )}
                    {metric.limit === -1 && (
                      <span className="text-muted-foreground">unlimited</span>
                    )}
                  </div>
                </div>
                
                {metric.limit !== -1 ? (
                  <div className="space-y-1">
                    <Progress 
                      value={metric.percentage} 
                      className="h-2"
                      // You might need to customize this based on your Progress component
                    />
                    <div className="text-right">
                      <span className={`text-xs ${getStatusColor(metric.percentage)}`}>
                        {metric.percentage.toFixed(1)}% used
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="h-2 bg-green-100 rounded-full">
                    <div className="h-full w-full bg-green-500 rounded-full" />
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Usage Chart */}
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="name" 
                  tick={{ fontSize: 12 }}
                  angle={-45}
                  textAnchor="end"
                  height={80}
                />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip 
                  formatter={(value, name, props) => {
                    const { payload } = props;
                    if (name === 'used') {
                      return [
                        `${value} (${payload.percentage.toFixed(1)}%)`,
                        'Used'
                      ];
                    }
                    if (name === 'limit' && payload.unlimited) {
                      return ['Unlimited', 'Limit'];
                    }
                    return [value, name === 'limit' ? 'Limit' : 'Used'];
                  }}
                  labelFormatter={(label) => `${label}`}
                />
                <Bar dataKey="used" name="used">
                  {chartData.map((entry, index) => (
                    <Cell 
                      key={`cell-${index}`} 
                      fill={
                        entry.percentage >= 90 ? '#ef4444' :
                        entry.percentage >= 70 ? '#f59e0b' : '#10b981'
                      }
                    />
                  ))}
                </Bar>
                <Bar dataKey="limit" name="limit" fill="#e5e7eb" opacity={0.3}>
                  {chartData.map((entry, index) => (
                    <Cell 
                      key={`cell-limit-${index}`} 
                      fill={entry.unlimited ? 'transparent' : '#e5e7eb'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default UsageChart;