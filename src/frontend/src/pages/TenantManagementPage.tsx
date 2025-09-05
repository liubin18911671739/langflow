import React, { useState, useEffect } from 'react';
import { 
  BuildingOfficeIcon, 
  UserGroupIcon, 
  CogIcon, 
  PlusIcon, 
  PencilIcon, 
  TrashIcon,
  ChartBarIcon
} from '@heroicons/react/24/outline';
import { Tab } from '@headlessui/react';
import TenantSelector from '../components/tenant/TenantSelector';

interface Organization {
  id: string;
  name: string;
  display_name?: string;
  is_personal: boolean;
  tier: string;
  created_at: string;
  subscription?: {
    plan_name: string;
    status: string;
    current_period_end: string;
  };
  usage?: {
    flows: number;
    variables: number;
    api_calls: number;
    storage_mb: number;
  };
  limits?: {
    max_flows: number;
    max_variables: number;
    max_api_calls: number;
    max_storage_mb: number;
  };
}

interface Member {
  id: string;
  email: string;
  name: string;
  role: string;
  joined_at: string;
  last_active: string;
}

const TenantManagementPage: React.FC = () => {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [currentOrganization, setCurrentOrganization] = useState<Organization | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTab, setSelectedTab] = useState(0);

  const tabs = [
    { name: 'Overview', icon: ChartBarIcon },
    { name: 'Members', icon: UserGroupIcon },
    { name: 'Settings', icon: CogIcon },
  ];

  useEffect(() => {
    loadOrganizations();
  }, []);

  useEffect(() => {
    if (currentOrganization) {
      loadOrganizationDetails();
      loadMembers();
    }
  }, [currentOrganization]);

  const loadOrganizations = async () => {
    try {
      // Mock API call - replace with actual API
      const mockOrganizations: Organization[] = [
        {
          id: '1',
          name: 'personal',
          display_name: 'My Personal Account',
          is_personal: true,
          tier: 'FREE',
          created_at: '2024-01-01T00:00:00Z',
          usage: {
            flows: 5,
            variables: 12,
            api_calls: 150,
            storage_mb: 25
          },
          limits: {
            max_flows: 10,
            max_variables: 50,
            max_api_calls: 1000,
            max_storage_mb: 100
          }
        },
        {
          id: '2',
          name: 'acme-corp',
          display_name: 'ACME Corporation',
          is_personal: false,
          tier: 'PROFESSIONAL',
          created_at: '2024-02-01T00:00:00Z',
          subscription: {
            plan_name: 'Professional',
            status: 'active',
            current_period_end: '2024-12-01T00:00:00Z'
          },
          usage: {
            flows: 25,
            variables: 80,
            api_calls: 5000,
            storage_mb: 500
          },
          limits: {
            max_flows: 100,
            max_variables: 500,
            max_api_calls: 50000,
            max_storage_mb: 5000
          }
        }
      ];
      setOrganizations(mockOrganizations);
      setCurrentOrganization(mockOrganizations[0]);
    } catch (error) {
      console.error('Failed to load organizations:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadOrganizationDetails = async () => {
    // Mock API call for organization details
    console.log('Loading details for organization:', currentOrganization?.id);
  };

  const loadMembers = async () => {
    if (!currentOrganization || currentOrganization.is_personal) {
      setMembers([]);
      return;
    }

    try {
      // Mock API call - replace with actual API
      const mockMembers: Member[] = [
        {
          id: '1',
          email: 'admin@acme.com',
          name: 'John Admin',
          role: 'admin',
          joined_at: '2024-02-01T00:00:00Z',
          last_active: '2024-02-28T15:30:00Z'
        },
        {
          id: '2',
          email: 'developer@acme.com',
          name: 'Jane Developer',
          role: 'member',
          joined_at: '2024-02-15T00:00:00Z',
          last_active: '2024-02-28T12:00:00Z'
        }
      ];
      setMembers(mockMembers);
    } catch (error) {
      console.error('Failed to load members:', error);
    }
  };

  const formatUsagePercentage = (used: number, limit: number): number => {
    return Math.round((used / limit) * 100);
  };

  const getUsageColor = (percentage: number): string => {
    if (percentage >= 90) return 'bg-red-500';
    if (percentage >= 75) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  const formatRole = (role: string): string => {
    return role.charAt(0).toUpperCase() + role.slice(1);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="p-6 bg-gray-50 dark:bg-gray-900 min-h-screen">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-4">
            Organization Management
          </h1>
          
          <div className="flex items-center justify-between">
            <div className="flex-1 max-w-sm">
              <TenantSelector
                currentOrganization={currentOrganization}
                organizations={organizations}
                onOrganizationChange={setCurrentOrganization}
                onCreateOrganization={() => console.log('Create organization')}
              />
            </div>
          </div>
        </div>

        {currentOrganization && (
          <>
            {/* Organization Info Card */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 mb-6">
              <div className="p-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center">
                    <BuildingOfficeIcon className="h-8 w-8 text-gray-400 mr-3" />
                    <div>
                      <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                        {currentOrganization.display_name || currentOrganization.name}
                      </h2>
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        {currentOrganization.is_personal ? 'Personal Account' : 'Team Organization'} • 
                        Created {formatDate(currentOrganization.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                      currentOrganization.tier === 'FREE' 
                        ? 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
                        : 'bg-blue-100 text-blue-800 dark:bg-blue-800 dark:text-blue-100'
                    }`}>
                      {currentOrganization.tier}
                    </span>
                  </div>
                </div>

                {currentOrganization.subscription && (
                  <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 mb-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-medium text-blue-900 dark:text-blue-100">
                          {currentOrganization.subscription.plan_name} Plan
                        </p>
                        <p className="text-sm text-blue-700 dark:text-blue-300">
                          Renews on {formatDate(currentOrganization.subscription.current_period_end)}
                        </p>
                      </div>
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                        currentOrganization.subscription.status === 'active'
                          ? 'bg-green-100 text-green-800 dark:bg-green-800 dark:text-green-100'
                          : 'bg-red-100 text-red-800 dark:bg-red-800 dark:text-red-100'
                      }`}>
                        {currentOrganization.subscription.status}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Tabs */}
            <Tab.Group selectedIndex={selectedTab} onChange={setSelectedTab}>
              <Tab.List className="flex space-x-1 rounded-xl bg-blue-900/20 p-1 mb-6">
                {tabs.map((tab) => (
                  <Tab
                    key={tab.name}
                    className={({ selected }) =>
                      `w-full rounded-lg py-2.5 text-sm font-medium leading-5 text-blue-700 dark:text-blue-100 ${
                        selected
                          ? 'bg-white dark:bg-gray-800 shadow'
                          : 'text-blue-100 hover:bg-white/[0.12] hover:text-white'
                      }`
                    }
                  >
                    <div className="flex items-center justify-center space-x-2">
                      <tab.icon className="h-4 w-4" />
                      <span>{tab.name}</span>
                    </div>
                  </Tab>
                ))}
              </Tab.List>

              <Tab.Panels>
                {/* Overview Panel */}
                <Tab.Panel>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                    {currentOrganization.usage && currentOrganization.limits && (
                      <>
                        {/* Flows Usage */}
                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                          <div className="flex items-center justify-between mb-4">
                            <h3 className="text-sm font-medium text-gray-900 dark:text-white">Flows</h3>
                            <span className="text-sm text-gray-500 dark:text-gray-400">
                              {currentOrganization.usage.flows} / {currentOrganization.limits.max_flows}
                            </span>
                          </div>
                          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                            <div 
                              className={`h-2 rounded-full ${getUsageColor(
                                formatUsagePercentage(currentOrganization.usage.flows, currentOrganization.limits.max_flows)
                              )}`}
                              style={{
                                width: `${formatUsagePercentage(currentOrganization.usage.flows, currentOrganization.limits.max_flows)}%`
                              }}
                            />
                          </div>
                        </div>

                        {/* Variables Usage */}
                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                          <div className="flex items-center justify-between mb-4">
                            <h3 className="text-sm font-medium text-gray-900 dark:text-white">Variables</h3>
                            <span className="text-sm text-gray-500 dark:text-gray-400">
                              {currentOrganization.usage.variables} / {currentOrganization.limits.max_variables}
                            </span>
                          </div>
                          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                            <div 
                              className={`h-2 rounded-full ${getUsageColor(
                                formatUsagePercentage(currentOrganization.usage.variables, currentOrganization.limits.max_variables)
                              )}`}
                              style={{
                                width: `${formatUsagePercentage(currentOrganization.usage.variables, currentOrganization.limits.max_variables)}%`
                              }}
                            />
                          </div>
                        </div>

                        {/* API Calls Usage */}
                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                          <div className="flex items-center justify-between mb-4">
                            <h3 className="text-sm font-medium text-gray-900 dark:text-white">API Calls</h3>
                            <span className="text-sm text-gray-500 dark:text-gray-400">
                              {currentOrganization.usage.api_calls.toLocaleString()} / {currentOrganization.limits.max_api_calls.toLocaleString()}
                            </span>
                          </div>
                          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                            <div 
                              className={`h-2 rounded-full ${getUsageColor(
                                formatUsagePercentage(currentOrganization.usage.api_calls, currentOrganization.limits.max_api_calls)
                              )}`}
                              style={{
                                width: `${formatUsagePercentage(currentOrganization.usage.api_calls, currentOrganization.limits.max_api_calls)}%`
                              }}
                            />
                          </div>
                        </div>

                        {/* Storage Usage */}
                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                          <div className="flex items-center justify-between mb-4">
                            <h3 className="text-sm font-medium text-gray-900 dark:text-white">Storage</h3>
                            <span className="text-sm text-gray-500 dark:text-gray-400">
                              {currentOrganization.usage.storage_mb} MB / {currentOrganization.limits.max_storage_mb} MB
                            </span>
                          </div>
                          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                            <div 
                              className={`h-2 rounded-full ${getUsageColor(
                                formatUsagePercentage(currentOrganization.usage.storage_mb, currentOrganization.limits.max_storage_mb)
                              )}`}
                              style={{
                                width: `${formatUsagePercentage(currentOrganization.usage.storage_mb, currentOrganization.limits.max_storage_mb)}%`
                              }}
                            />
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                </Tab.Panel>

                {/* Members Panel */}
                <Tab.Panel>
                  <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
                    <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                      <div className="flex items-center justify-between">
                        <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                          Team Members
                        </h3>
                        {!currentOrganization.is_personal && (
                          <button className="inline-flex items-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">
                            <PlusIcon className="h-4 w-4 mr-1" />
                            Invite Member
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="divide-y divide-gray-200 dark:divide-gray-700">
                      {currentOrganization.is_personal ? (
                        <div className="p-6 text-center text-gray-500 dark:text-gray-400">
                          <UserGroupIcon className="h-12 w-12 mx-auto mb-4 text-gray-300 dark:text-gray-600" />
                          <p>Personal accounts don't have team members.</p>
                          <p className="text-sm mt-1">Upgrade to a team plan to collaborate with others.</p>
                        </div>
                      ) : (
                        members.map((member) => (
                          <div key={member.id} className="p-6">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center">
                                <div className="h-10 w-10 rounded-full bg-gray-300 dark:bg-gray-600 flex items-center justify-center">
                                  <span className="text-sm font-medium text-gray-700 dark:text-gray-200">
                                    {member.name.charAt(0)}
                                  </span>
                                </div>
                                <div className="ml-4">
                                  <div className="text-sm font-medium text-gray-900 dark:text-white">
                                    {member.name}
                                  </div>
                                  <div className="text-sm text-gray-500 dark:text-gray-400">
                                    {member.email}
                                  </div>
                                  <div className="text-xs text-gray-400 dark:text-gray-500">
                                    Last active {formatDate(member.last_active)}
                                  </div>
                                </div>
                              </div>
                              <div className="flex items-center space-x-2">
                                <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                  member.role === 'admin'
                                    ? 'bg-purple-100 text-purple-800 dark:bg-purple-800 dark:text-purple-100'
                                    : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'
                                }`}>
                                  {formatRole(member.role)}
                                </span>
                                <button className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                                  <PencilIcon className="h-4 w-4" />
                                </button>
                                <button className="text-gray-400 hover:text-red-600 dark:hover:text-red-400">
                                  <TrashIcon className="h-4 w-4" />
                                </button>
                              </div>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </Tab.Panel>

                {/* Settings Panel */}
                <Tab.Panel>
                  <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                    <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                      Organization Settings
                    </h3>
                    <div className="space-y-6">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                          Organization Name
                        </label>
                        <input
                          type="text"
                          className="mt-1 block w-full border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                          defaultValue={currentOrganization.display_name || currentOrganization.name}
                        />
                      </div>
                      
                      <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                        <h4 className="text-md font-medium text-red-900 dark:text-red-100 mb-2">
                          Danger Zone
                        </h4>
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                          These actions cannot be undone. Please proceed with caution.
                        </p>
                        <button className="inline-flex items-center px-3 py-2 border border-red-300 text-sm leading-4 font-medium rounded-md text-red-700 dark:text-red-100 bg-white dark:bg-red-900/20 hover:bg-red-50 dark:hover:bg-red-900/40 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500">
                          <TrashIcon className="h-4 w-4 mr-1" />
                          Delete Organization
                        </button>
                      </div>
                    </div>
                  </div>
                </Tab.Panel>
              </Tab.Panels>
            </Tab.Group>
          </>
        )}
      </div>
    </div>
  );
};

export default TenantManagementPage;