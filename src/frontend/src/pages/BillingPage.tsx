import React from 'react';
import BillingDashboard from '../components/billing/BillingDashboard';

const BillingPage: React.FC = () => {
  return (
    <div className="container mx-auto px-4 py-8 max-w-7xl">
      <BillingDashboard />
    </div>
  );
};

export default BillingPage;