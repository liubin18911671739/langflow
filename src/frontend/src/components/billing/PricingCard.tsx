import React from 'react';
import { Check, X, Zap } from 'lucide-react';
import { Button } from '../ui/button';

interface PricingFeature {
  name: string;
  included: boolean;
}

interface PricingCardProps {
  plan: {
    id: string;
    name: string;
    plan_type: string;
    description: string;
    price: number;
    yearly_price?: number;
    currency: string;
    limits: Record<string, number>;
    features: string[];
    is_active: boolean;
    is_popular: boolean;
  };
  isYearly: boolean;
  isCurrentPlan?: boolean;
  onSelect: (planId: string) => void;
  loading?: boolean;
}

const PricingCard: React.FC<PricingCardProps> = ({
  plan,
  isYearly,
  isCurrentPlan = false,
  onSelect,
  loading = false,
}) => {
  const price = isYearly ? plan.yearly_price || plan.price * 12 : plan.price;
  const monthlyPrice = isYearly ? (plan.yearly_price || plan.price * 12) / 12 : plan.price;
  
  const formatLimit = (key: string, value: number) => {
    if (value === -1) return 'Unlimited';
    if (key === 'storage_mb') return `${value} MB`;
    if (key === 'team_members') return `${value} users`;
    return value.toLocaleString();
  };

  const getFeatureList = (): PricingFeature[] => {
    const baseFeatures: PricingFeature[] = [
      { name: `${formatLimit('api_calls', plan.limits.api_calls || 0)} API calls/month`, included: true },
      { name: `${formatLimit('flow_executions', plan.limits.flow_executions || 0)} flow executions/month`, included: true },
      { name: `${formatLimit('storage_mb', plan.limits.storage_mb || 0)} storage`, included: true },
      { name: `${formatLimit('team_members', plan.limits.team_members || 1)} team members`, included: true },
    ];

    const planFeatures: PricingFeature[] = plan.features.map((feature) => ({
      name: formatFeatureName(feature),
      included: true,
    }));

    return [...baseFeatures, ...planFeatures];
  };

  const formatFeatureName = (feature: string): string => {
    const featureNames: Record<string, string> = {
      'basic_components': 'Basic components',
      'advanced_components': 'Advanced components',
      'premium_components': 'Premium components',
      'unlimited_everything': 'Unlimited everything',
      'community_support': 'Community support',
      'email_support': 'Email support',
      'priority_support': 'Priority support',
      'dedicated_support': '24/7 dedicated support',
      'basic_analytics': 'Basic analytics',
      'advanced_analytics': 'Advanced analytics',
      'custom_integrations': 'Custom integrations',
      'sso': 'Single Sign-On (SSO)',
      'custom_deployment': 'Custom deployment',
      'advanced_security': 'Advanced security',
      'audit_logs': 'Audit logs',
      'white_label': 'White label branding',
    };
    
    return featureNames[feature] || feature.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  };

  return (
    <div className={`
      relative rounded-lg border-2 p-6 shadow-sm transition-all hover:shadow-md
      ${plan.is_popular ? 'border-primary bg-primary/5' : 'border-border bg-background'}
      ${isCurrentPlan ? 'ring-2 ring-primary ring-offset-2' : ''}
    `}>
      {plan.is_popular && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <div className="flex items-center gap-1 rounded-full bg-primary px-3 py-1 text-sm font-medium text-primary-foreground">
            <Zap className="h-3 w-3" />
            Most Popular
          </div>
        </div>
      )}
      
      <div className="text-center">
        <h3 className="text-lg font-semibold">{plan.name}</h3>
        <p className="mt-2 text-sm text-muted-foreground">{plan.description}</p>
        
        <div className="mt-4">
          {plan.price === 0 ? (
            <div className="text-3xl font-bold">Free</div>
          ) : (
            <div>
              <div className="text-3xl font-bold">
                ${monthlyPrice.toFixed(0)}
                <span className="text-lg font-normal text-muted-foreground">/month</span>
              </div>
              {isYearly && plan.yearly_price && (
                <div className="text-sm text-muted-foreground">
                  Billed annually (${price.toFixed(0)})
                </div>
              )}
            </div>
          )}
        </div>

        <Button
          className="mt-6 w-full"
          variant={plan.is_popular ? "default" : "outline"}
          onClick={() => onSelect(plan.id)}
          disabled={loading || isCurrentPlan}
        >
          {loading ? (
            <>
              <div className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
              Processing...
            </>
          ) : isCurrentPlan ? (
            'Current Plan'
          ) : plan.price === 0 ? (
            'Get Started'
          ) : (
            'Subscribe Now'
          )}
        </Button>
      </div>

      <div className="mt-6">
        <h4 className="font-medium text-sm text-muted-foreground uppercase tracking-wide">
          What's included
        </h4>
        <ul className="mt-4 space-y-3">
          {getFeatureList().map((feature, index) => (
            <li key={index} className="flex items-start gap-3">
              {feature.included ? (
                <Check className="h-4 w-4 text-green-500 mt-0.5 flex-shrink-0" />
              ) : (
                <X className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
              )}
              <span className={`text-sm ${feature.included ? 'text-foreground' : 'text-muted-foreground'}`}>
                {feature.name}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export default PricingCard;