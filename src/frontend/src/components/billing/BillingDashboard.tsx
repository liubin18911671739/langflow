import React, { useState, useEffect } from 'react';
import { AlertCircle, CreditCard, FileText, Settings, TrendingUp } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Alert, AlertDescription } from '../ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import PricingCard from './PricingCard';
import UsageChart from './UsageChart';
import { api } from '../../api/api';

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

interface Invoice {
  id: string;
  invoice_number: string;
  amount: number;
  currency: string;
  status: string;
  period_start: string;
  period_end: string;
  created_at: string;
  hosted_invoice_url?: string;
}

const BillingDashboard: React.FC = () => {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [selectedOrg, setSelectedOrg] = useState<Organization | null>(null);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [currentSubscription, setCurrentSubscription] = useState<CurrentSubscription | null>(null);
  const [usageSummary, setUsageSummary] = useState<UsageSummary | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [isYearlyPricing, setIsYearlyPricing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [subscribingPlan, setSubscribingPlan] = useState<string | null>(null);

  useEffect(() => {
    loadInitialData();
  }, []);

  useEffect(() => {
    if (selectedOrg) {
      loadOrganizationData();
    }
  }, [selectedOrg]);

  const loadInitialData = async () => {
    try {
      setLoading(true);
      
      // Load organizations
      const orgsResponse = await api.get('/api/v1/billing/organizations');
      const orgsData = orgsResponse.data;
      setOrganizations(orgsData);
      
      if (orgsData.length > 0) {
        setSelectedOrg(orgsData[0]);
      }
      
      // Load subscription plans
      const plansResponse = await api.get('/api/v1/billing/plans');
      setPlans(plansResponse.data);
      
    } catch (error) {
      console.error('Failed to load initial data:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadOrganizationData = async () => {
    if (!selectedOrg) return;
    
    try {
      // Load current subscription
      const subResponse = await api.get(`/api/v1/billing/organizations/${selectedOrg.id}/subscription`);
      setCurrentSubscription(subResponse.data);
    } catch (error) {
      // No subscription found
      setCurrentSubscription(null);
    }

    try {
      // Load usage summary
      const usageResponse = await api.get(`/api/v1/billing/organizations/${selectedOrg.id}/usage`);
      setUsageSummary(usageResponse.data);
    } catch (error) {
      console.error('Failed to load usage data:', error);
    }

    try {
      // Load invoices
      const invoicesResponse = await api.get(`/api/v1/billing/organizations/${selectedOrg.id}/invoices`);
      setInvoices(invoicesResponse.data.invoices || []);
    } catch (error) {
      console.error('Failed to load invoices:', error);
    }
  };

  const handleSubscribe = async (planId: string) => {
    if (!selectedOrg) return;
    
    try {
      setSubscribingPlan(planId);
      
      const response = await api.post(`/api/v1/billing/organizations/${selectedOrg.id}/subscription`, {
        plan_id: planId,
        is_yearly: isYearlyPricing,
        trial_days: 14
      });

      if (response.data.client_secret) {
        // Handle Stripe payment flow here
        // This would integrate with Stripe.js
        console.log('Payment required:', response.data.client_secret);
      }

      // Reload subscription data
      await loadOrganizationData();
      
    } catch (error) {
      console.error('Failed to create subscription:', error);
    } finally {
      setSubscribingPlan(null);
    }
  };

  const handleBillingPortal = async () => {
    if (!selectedOrg) return;
    
    try {
      const response = await api.post(`/api/v1/billing/organizations/${selectedOrg.id}/billing-portal`, {
        return_url: window.location.href
      });
      
      window.open(response.data.url, '_blank');
    } catch (error) {
      console.error('Failed to create billing portal session:', error);
    }
  };

  const formatCurrency = (amount: number, currency: string) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency.toUpperCase()
    }).format(amount);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString();
  };

  const getUsageMetrics = () => {
    if (!usageSummary) return [];
    
    return Object.entries(usageSummary.metrics).map(([key, value]) => ({
      name: key,
      value,
      limit: usageSummary.limits[key] || 0,
      percentage: usageSummary.usage_percentage[key] || 0,
      unit: key.includes('storage') ? 'mb' : 'count'
    }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent mx-auto mb-4" />
          <p>Loading billing dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Billing & Usage</h1>
          <p className="text-muted-foreground">
            Manage your subscription and monitor usage
          </p>
        </div>
        
        {selectedOrg && (
          <div className="flex items-center gap-2">
            <select 
              value={selectedOrg.id}
              onChange={(e) => {
                const org = organizations.find(o => o.id === e.target.value);
                setSelectedOrg(org || null);
              }}
              className="rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              {organizations.map(org => (
                <option key={org.id} value={org.id}>{org.name}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Current Subscription Status */}
      {currentSubscription && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CreditCard className="h-5 w-5" />
              Current Subscription
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Plan</p>
                <p className="font-semibold">{currentSubscription.plan.name}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <p className="font-semibold capitalize">{currentSubscription.status}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Billing Cycle</p>
                <p className="font-semibold">{currentSubscription.is_yearly ? 'Yearly' : 'Monthly'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Next Billing Date</p>
                <p className="font-semibold">{formatDate(currentSubscription.current_period_end)}</p>
              </div>
            </div>
            
            <div className="mt-4 flex gap-2">
              <Button onClick={handleBillingPortal} variant="outline">
                <Settings className="h-4 w-4 mr-2" />
                Manage Subscription
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue={currentSubscription ? "usage" : "plans"} className="space-y-6">
        <TabsList>
          <TabsTrigger value="usage" className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Usage
          </TabsTrigger>
          <TabsTrigger value="plans" className="flex items-center gap-2">
            <CreditCard className="h-4 w-4" />
            Plans
          </TabsTrigger>
          <TabsTrigger value="billing" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Billing History
          </TabsTrigger>
        </TabsList>

        <TabsContent value="usage" className="space-y-6">
          {usageSummary ? (
            <UsageChart metrics={getUsageMetrics()} />
          ) : (
            <Card>
              <CardContent className="py-8">
                <div className="text-center text-muted-foreground">
                  No usage data available
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="plans" className="space-y-6">
          {/* Billing Toggle */}
          <div className="flex justify-center">
            <div className="flex items-center space-x-2 bg-muted p-1 rounded-lg">
              <button
                className={`px-3 py-1 rounded-md text-sm transition-colors ${
                  !isYearlyPricing ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground'
                }`}
                onClick={() => setIsYearlyPricing(false)}
              >
                Monthly
              </button>
              <button
                className={`px-3 py-1 rounded-md text-sm transition-colors ${
                  isYearlyPricing ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground'
                }`}
                onClick={() => setIsYearlyPricing(true)}
              >
                Yearly
                <span className="ml-1 text-green-600">Save 20%</span>
              </button>
            </div>
          </div>

          {/* Pricing Cards */}
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {plans.map(plan => (
              <PricingCard
                key={plan.id}
                plan={plan}
                isYearly={isYearlyPricing}
                isCurrentPlan={currentSubscription?.plan.id === plan.id}
                onSelect={handleSubscribe}
                loading={subscribingPlan === plan.id}
              />
            ))}
          </div>
        </TabsContent>

        <TabsContent value="billing" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Billing History</CardTitle>
            </CardHeader>
            <CardContent>
              {invoices.length > 0 ? (
                <div className="space-y-4">
                  {invoices.map(invoice => (
                    <div key={invoice.id} className="flex items-center justify-between p-4 border rounded-lg">
                      <div>
                        <p className="font-medium">{invoice.invoice_number}</p>
                        <p className="text-sm text-muted-foreground">
                          {formatDate(invoice.period_start)} - {formatDate(invoice.period_end)}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="font-medium">{formatCurrency(invoice.amount, invoice.currency)}</p>
                        <p className={`text-sm capitalize ${
                          invoice.status === 'paid' ? 'text-green-600' : 'text-yellow-600'
                        }`}>
                          {invoice.status}
                        </p>
                      </div>
                      {invoice.hosted_invoice_url && (
                        <Button variant="outline" size="sm" asChild>
                          <a href={invoice.hosted_invoice_url} target="_blank" rel="noopener noreferrer">
                            View Invoice
                          </a>
                        </Button>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center text-muted-foreground py-8">
                  No billing history available
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default BillingDashboard;