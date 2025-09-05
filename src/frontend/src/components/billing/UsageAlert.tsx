import React from 'react';
import { AlertTriangle, TrendingUp, Zap } from 'lucide-react';
import { Alert, AlertDescription } from '../ui/alert';
import { Button } from '../ui/button';
import { Progress } from '../ui/progress';

interface UsageAlertProps {
  metric: {
    name: string;
    percentage: number;
    current: number;
    limit: number;
    unit: string;
  };
  onUpgrade?: () => void;
}

const UsageAlert: React.FC<UsageAlertProps> = ({ metric, onUpgrade }) => {
  const getSeverity = (percentage: number) => {
    if (percentage >= 95) return 'critical';
    if (percentage >= 80) return 'warning';
    return 'info';
  };

  const getIcon = (severity: string) => {
    switch (severity) {
      case 'critical':
        return <AlertTriangle className="h-4 w-4 text-red-500" />;
      case 'warning':
        return <TrendingUp className="h-4 w-4 text-yellow-500" />;
      default:
        return <Zap className="h-4 w-4 text-blue-500" />;
    }
  };

  const getAlertStyle = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'border-red-200 bg-red-50 text-red-800';
      case 'warning':
        return 'border-yellow-200 bg-yellow-50 text-yellow-800';
      default:
        return 'border-blue-200 bg-blue-50 text-blue-800';
    }
  };

  const formatValue = (value: number, unit: string) => {
    if (unit === 'mb') {
      if (value >= 1024) {
        return `${(value / 1024).toFixed(1)} GB`;
      }
      return `${value} MB`;
    }
    return value.toLocaleString();
  };

  const severity = getSeverity(metric.percentage);

  return (
    <Alert className={getAlertStyle(severity)}>
      <div className="flex items-start gap-3">
        {getIcon(severity)}
        <div className="flex-1 space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="font-medium">
              {severity === 'critical' ? 'Usage Limit Exceeded' : 
               severity === 'warning' ? 'Usage Warning' : 'Usage Update'}
            </h4>
            <span className="text-sm font-mono">
              {metric.percentage.toFixed(1)}%
            </span>
          </div>
          
          <AlertDescription>
            <div className="space-y-2">
              <p>
                Your {metric.name.toLowerCase()} usage is at{' '}
                <strong>{formatValue(metric.current, metric.unit)}</strong> out of{' '}
                <strong>{formatValue(metric.limit, metric.unit)}</strong>
              </p>
              
              <Progress value={metric.percentage} className="h-2" />
              
              {severity === 'critical' && (
                <p className="text-sm">
                  You have exceeded your usage limit. Some features may be restricted until your next billing cycle or you upgrade your plan.
                </p>
              )}
              
              {severity === 'warning' && (
                <p className="text-sm">
                  You're approaching your usage limit. Consider upgrading your plan to avoid service interruptions.
                </p>
              )}
            </div>
          </AlertDescription>
          
          {(severity === 'critical' || severity === 'warning') && onUpgrade && (
            <div className="pt-2">
              <Button 
                size="sm" 
                variant={severity === 'critical' ? 'default' : 'outline'}
                onClick={onUpgrade}
              >
                Upgrade Plan
              </Button>
            </div>
          )}
        </div>
      </div>
    </Alert>
  );
};

export default UsageAlert;