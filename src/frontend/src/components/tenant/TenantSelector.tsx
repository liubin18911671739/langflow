import React, { useState, useEffect } from 'react';
import { ChevronDownIcon, CheckIcon, BuildingOfficeIcon, PlusIcon } from '@heroicons/react/24/outline';
import { Listbox, Transition } from '@headlessui/react';

interface Organization {
  id: string;
  name: string;
  display_name?: string;
  is_personal: boolean;
  tier: string;
}

interface TenantSelectorProps {
  currentOrganization: Organization | null;
  organizations: Organization[];
  onOrganizationChange: (org: Organization) => void;
  onCreateOrganization?: () => void;
  className?: string;
}

const TenantSelector: React.FC<TenantSelectorProps> = ({
  currentOrganization,
  organizations,
  onOrganizationChange,
  onCreateOrganization,
  className = "",
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const handleChange = (organization: Organization) => {
    onOrganizationChange(organization);
    setIsOpen(false);
  };

  return (
    <div className={`relative ${className}`}>
      <Listbox value={currentOrganization} onChange={handleChange}>
        <div className="relative">
          <Listbox.Button className="relative w-full cursor-default rounded-lg bg-white dark:bg-gray-800 py-2 pl-3 pr-10 text-left shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-opacity-75 focus:ring-offset-2 focus:ring-offset-orange-300 sm:text-sm border border-gray-300 dark:border-gray-600">
            <span className="flex items-center">
              <BuildingOfficeIcon className="h-5 w-5 text-gray-400 mr-2" />
              <span className="block truncate">
                {currentOrganization 
                  ? (currentOrganization.display_name || currentOrganization.name)
                  : 'Select Organization'
                }
              </span>
              {currentOrganization && (
                <span className={`ml-2 px-2 py-0.5 text-xs rounded-full ${
                  currentOrganization.is_personal 
                    ? 'bg-blue-100 text-blue-800 dark:bg-blue-800 dark:text-blue-100' 
                    : 'bg-green-100 text-green-800 dark:bg-green-800 dark:text-green-100'
                }`}>
                  {currentOrganization.is_personal ? 'Personal' : currentOrganization.tier}
                </span>
              )}
            </span>
            <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
              <ChevronDownIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
            </span>
          </Listbox.Button>

          <Transition
            show={isOpen}
            as={React.Fragment}
            leave="transition ease-in duration-100"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <Listbox.Options className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md bg-white dark:bg-gray-800 py-1 text-base shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none sm:text-sm">
              {organizations.map((organization) => (
                <Listbox.Option
                  key={organization.id}
                  className={({ active }) =>
                    `relative cursor-default select-none py-2 pl-10 pr-4 ${
                      active 
                        ? 'bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100' 
                        : 'text-gray-900 dark:text-gray-100'
                    }`
                  }
                  value={organization}
                >
                  {({ selected }) => (
                    <>
                      <div className="flex items-center">
                        <BuildingOfficeIcon className="h-5 w-5 text-gray-400 mr-2" />
                        <div className="flex-1">
                          <span className={`block truncate ${selected ? 'font-medium' : 'font-normal'}`}>
                            {organization.display_name || organization.name}
                          </span>
                          <span className="block truncate text-sm text-gray-500 dark:text-gray-400">
                            {organization.is_personal ? 'Personal Account' : `Team • ${organization.tier}`}
                          </span>
                        </div>
                        <span className={`px-2 py-0.5 text-xs rounded-full ${
                          organization.is_personal 
                            ? 'bg-blue-100 text-blue-800 dark:bg-blue-800 dark:text-blue-100' 
                            : 'bg-green-100 text-green-800 dark:bg-green-800 dark:text-green-100'
                        }`}>
                          {organization.is_personal ? 'Personal' : organization.tier}
                        </span>
                      </div>
                      {selected ? (
                        <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-blue-600 dark:text-blue-400">
                          <CheckIcon className="h-5 w-5" aria-hidden="true" />
                        </span>
                      ) : null}
                    </>
                  )}
                </Listbox.Option>
              ))}
              
              {onCreateOrganization && (
                <>
                  <div className="border-t border-gray-200 dark:border-gray-700 my-1" />
                  <button
                    onClick={onCreateOrganization}
                    className="w-full text-left relative cursor-default select-none py-2 pl-10 pr-4 text-gray-900 dark:text-gray-100 hover:bg-blue-100 dark:hover:bg-blue-900"
                  >
                    <div className="flex items-center">
                      <PlusIcon className="h-5 w-5 text-gray-400 mr-2" />
                      <span className="block truncate font-medium">Create New Organization</span>
                    </div>
                  </button>
                </>
              )}
            </Listbox.Options>
          </Transition>
        </div>
      </Listbox>
    </div>
  );
};

export default TenantSelector;