import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';

interface Organization {
  id: string;
  name: string;
  display_name?: string;
  is_personal: boolean;
  tier: string;
  created_at: string;
}

interface TenantContextType {
  currentOrganization: Organization | null;
  organizations: Organization[];
  setCurrentOrganization: (org: Organization | null) => void;
  setOrganizations: (orgs: Organization[]) => void;
  isLoading: boolean;
  error: string | null;
  switchOrganization: (orgId: string) => Promise<void>;
  refreshOrganizations: () => Promise<void>;
}

const TenantContext = createContext<TenantContextType | undefined>(undefined);

interface TenantProviderProps {
  children: ReactNode;
}

export const TenantProvider: React.FC<TenantProviderProps> = ({ children }) => {
  const [currentOrganization, setCurrentOrganization] = useState<Organization | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Initialize tenant context on mount
  useEffect(() => {
    initializeTenantContext();
  }, []);

  // Update HTTP headers when organization changes
  useEffect(() => {
    if (currentOrganization) {
      updateHttpHeaders(currentOrganization.id);
      // Store current organization in localStorage for persistence
      localStorage.setItem('currentOrganizationId', currentOrganization.id);
    }
  }, [currentOrganization]);

  const initializeTenantContext = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Load organizations from API
      const orgs = await fetchOrganizations();
      setOrganizations(orgs);

      // Set current organization from localStorage or default to first
      const savedOrgId = localStorage.getItem('currentOrganizationId');
      const currentOrg = savedOrgId 
        ? orgs.find(org => org.id === savedOrgId) || orgs[0]
        : orgs[0];
      
      setCurrentOrganization(currentOrg || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initialize tenant context');
      console.error('Failed to initialize tenant context:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchOrganizations = async (): Promise<Organization[]> => {
    // Mock API call - replace with actual API endpoint
    // In a real app, this would be: await api.get('/api/v1/billing/organizations')
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve([
          {
            id: '1',
            name: 'personal',
            display_name: 'My Personal Account',
            is_personal: true,
            tier: 'FREE',
            created_at: '2024-01-01T00:00:00Z',
          },
          {
            id: '2',
            name: 'acme-corp',
            display_name: 'ACME Corporation',
            is_personal: false,
            tier: 'PROFESSIONAL',
            created_at: '2024-02-01T00:00:00Z',
          }
        ]);
      }, 1000);
    });
  };

  const updateHttpHeaders = (organizationId: string) => {
    // Set the X-Organization-ID header for all future requests
    // This would integrate with your HTTP client (axios, fetch, etc.)
    
    // Example with axios interceptor:
    /*
    axios.defaults.headers.common['X-Organization-ID'] = organizationId;
    */
    
    // Example with fetch wrapper:
    /*
    window.fetch = ((originalFetch) => {
      return (...args) => {
        if (args[1]) {
          args[1].headers = {
            ...args[1].headers,
            'X-Organization-ID': organizationId
          };
        } else {
          args[1] = {
            headers: { 'X-Organization-ID': organizationId }
          };
        }
        return originalFetch(...args);
      };
    })(window.fetch);
    */
    
    console.log(`Set organization context to: ${organizationId}`);
  };

  const switchOrganization = async (orgId: string) => {
    try {
      setIsLoading(true);
      setError(null);

      const org = organizations.find(o => o.id === orgId);
      if (!org) {
        throw new Error('Organization not found');
      }

      setCurrentOrganization(org);
      
      // Here you might want to refresh some data that's organization-specific
      // For example, refresh flows, variables, etc.
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to switch organization');
      console.error('Failed to switch organization:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const refreshOrganizations = async () => {
    try {
      setIsLoading(true);
      setError(null);

      const orgs = await fetchOrganizations();
      setOrganizations(orgs);

      // Update current organization if it still exists
      if (currentOrganization) {
        const updatedCurrentOrg = orgs.find(org => org.id === currentOrganization.id);
        if (updatedCurrentOrg) {
          setCurrentOrganization(updatedCurrentOrg);
        } else {
          // Current organization no longer exists, switch to first available
          setCurrentOrganization(orgs[0] || null);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh organizations');
      console.error('Failed to refresh organizations:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const value: TenantContextType = {
    currentOrganization,
    organizations,
    setCurrentOrganization,
    setOrganizations,
    isLoading,
    error,
    switchOrganization,
    refreshOrganizations,
  };

  return (
    <TenantContext.Provider value={value}>
      {children}
    </TenantContext.Provider>
  );
};

export const useTenant = (): TenantContextType => {
  const context = useContext(TenantContext);
  if (context === undefined) {
    throw new Error('useTenant must be used within a TenantProvider');
  }
  return context;
};

// Hook to get the current organization ID for API calls
export const useOrganizationId = (): string | null => {
  const { currentOrganization } = useTenant();
  return currentOrganization?.id || null;
};

// Hook to check if user can perform admin actions
export const useIsOrgAdmin = (): boolean => {
  const { currentOrganization } = useTenant();
  // In a real app, you'd check the user's role in the organization
  // For now, we'll assume personal accounts are admin and team accounts need role check
  return currentOrganization?.is_personal ?? false;
};

export default TenantContext;