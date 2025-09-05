import { useState, useEffect } from 'react';
import { api } from '../api/api';

interface Organization {
  id: string;
  name: string;
  slug: string;
}

interface SubscriptionPlan {
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
}

interface CurrentSubscription {
  id: string;
  status: string;
  is_yearly: boolean;
  current_period_start: string;
  current_period_end: string;
  trial_end?: string;
  cancel_at_period_end: boolean;
  plan: SubscriptionPlan;
}

interface UsageSummary {
  period_start: string;
  period_end: string;
  metrics: Record<string, number>;
  limits: Record<string, number>;
  usage_percentage: Record<string, number>;
}

interface UsageAlert {
  metric_type: string;
  usage_percentage: number;
  current_usage: number;
  limit: number;
  severity: 'warning' | 'critical';
  message: string;
}

export const useBilling = (organizationId?: string) => {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [currentSubscription, setCurrentSubscription] = useState<CurrentSubscription | null>(null);
  const [usageSummary, setUsageSummary] = useState<UsageSummary | null>(null);
  const [usageAlerts, setUsageAlerts] = useState<UsageAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load organizations
  const loadOrganizations = async () => {
    try {
      const response = await api.get('/api/v1/billing/organizations');
      setOrganizations(response.data);
      return response.data;
    } catch (err) {
      setError('Failed to load organizations');
      throw err;
    }
  };

  // Load subscription plans
  const loadPlans = async () => {
    try {
      const response = await api.get('/api/v1/billing/plans');
      setPlans(response.data);
      return response.data;
    } catch (err) {
      setError('Failed to load subscription plans');
      throw err;
    }
  };

  // Load current subscription for an organization
  const loadSubscription = async (orgId: string) => {
    try {
      const response = await api.get(`/api/v1/billing/organizations/${orgId}/subscription`);
      setCurrentSubscription(response.data);
      return response.data;
    } catch (err) {
      // No subscription found is not an error
      setCurrentSubscription(null);
      return null;
    }
  };

  // Load usage summary for an organization
  const loadUsageSummary = async (orgId: string) => {
    try {
      const response = await api.get(`/api/v1/billing/organizations/${orgId}/usage`);
      setUsageSummary(response.data);
      return response.data;
    } catch (err) {
      setError('Failed to load usage summary');
      throw err;
    }
  };

  // Load usage alerts for an organization
  const loadUsageAlerts = async (orgId: string, threshold = 0.8) => {
    try {
      const response = await api.get(`/api/v1/billing/organizations/${orgId}/usage/alerts`, {
        params: { warning_threshold: threshold }
      });
      setUsageAlerts(response.data.alerts || []);
      return response.data.alerts || [];
    } catch (err) {
      setError('Failed to load usage alerts');
      throw err;
    }
  };

  // Create a new subscription
  const createSubscription = async (
    orgId: string, 
    planId: string, 
    options: {
      isYearly?: boolean;
      trialDays?: number;
      paymentMethodId?: string;
    } = {}
  ) => {
    try {
      const response = await api.post(`/api/v1/billing/organizations/${orgId}/subscription`, {
        plan_id: planId,
        is_yearly: options.isYearly || false,
        trial_days: options.trialDays,
        payment_method_id: options.paymentMethodId
      });
      
      // Reload subscription data
      await loadSubscription(orgId);
      
      return response.data;
    } catch (err) {
      setError('Failed to create subscription');
      throw err;
    }
  };

  // Update subscription plan
  const updateSubscription = async (orgId: string, planId: string) => {
    try {
      const response = await api.put(`/api/v1/billing/organizations/${orgId}/subscription`, {
        plan_id: planId
      });
      
      // Reload subscription data
      await loadSubscription(orgId);
      
      return response.data;
    } catch (err) {
      setError('Failed to update subscription');
      throw err;
    }
  };

  // Cancel subscription
  const cancelSubscription = async (orgId: string, immediately = false) => {
    try {
      const response = await api.delete(`/api/v1/billing/organizations/${orgId}/subscription`, {
        params: { cancel_immediately: immediately }
      });
      
      // Reload subscription data
      await loadSubscription(orgId);
      
      return response.data;
    } catch (err) {
      setError('Failed to cancel subscription');
      throw err;
    }
  };

  // Create billing portal session
  const createBillingPortalSession = async (orgId: string, returnUrl?: string) => {
    try {
      const response = await api.post(`/api/v1/billing/organizations/${orgId}/billing-portal`, {
        return_url: returnUrl || window.location.href
      });
      
      return response.data.url;
    } catch (err) {
      setError('Failed to create billing portal session');
      throw err;
    }
  };

  // Check quota for a specific metric
  const checkQuota = async (orgId: string, metricType: string, requestedAmount = 1) => {
    try {
      const response = await api.get(`/api/v1/billing/organizations/${orgId}/usage/quota`, {
        params: { metric_type: metricType, requested_amount: requestedAmount }
      });
      
      return response.data;
    } catch (err) {
      setError('Failed to check quota');
      throw err;
    }
  };

  // Load all data for an organization
  const loadOrganizationData = async (orgId: string) => {
    setLoading(true);
    setError(null);
    
    try {
      await Promise.all([
        loadSubscription(orgId),
        loadUsageSummary(orgId),
        loadUsageAlerts(orgId)
      ]);
    } catch (err) {
      console.error('Error loading organization data:', err);
    } finally {
      setLoading(false);
    }
  };

  // Initialize data
  useEffect(() => {
    const initializeData = async () => {
      setLoading(true);
      setError(null);
      
      try {
        await Promise.all([
          loadOrganizations(),
          loadPlans()
        ]);
        
        if (organizationId) {
          await loadOrganizationData(organizationId);
        }
      } catch (err) {
        console.error('Error initializing billing data:', err);
      } finally {
        setLoading(false);
      }
    };

    initializeData();
  }, [organizationId]);

  return {
    // Data
    organizations,
    plans,
    currentSubscription,
    usageSummary,
    usageAlerts,
    loading,
    error,
    
    // Actions
    loadOrganizations,
    loadPlans,
    loadSubscription,
    loadUsageSummary,
    loadUsageAlerts,
    loadOrganizationData,
    createSubscription,
    updateSubscription,
    cancelSubscription,
    createBillingPortalSession,
    checkQuota,
    
    // Utilities
    setError
  };
};

// Utility functions
export const formatCurrency = (amount: number, currency = 'USD') => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency.toUpperCase()
  }).format(amount);
};

export const formatUsageMetric = (value: number, metricType: string) => {
  if (metricType.includes('storage')) {
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
  
  return value.toLocaleString();
};

export const getUsageStatus = (percentage: number) => {
  if (percentage >= 95) return { status: 'critical', color: 'red' };
  if (percentage >= 80) return { status: 'warning', color: 'yellow' };
  if (percentage >= 60) return { status: 'moderate', color: 'blue' };
  return { status: 'low', color: 'green' };
};