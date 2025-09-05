import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { 
  Bars3Icon,
  BellIcon,
  UserCircleIcon,
  CogIcon,
  ArrowRightOnRectangleIcon,
  MagnifyingGlassIcon
} from '@heroicons/react/24/outline';
import { Menu, Transition, Disclosure } from '@headlessui/react';
import TenantSelector from './TenantSelector';
import { useTenant } from '../../contexts/TenantContext';

interface NavbarProps {
  user?: {
    name: string;
    email: string;
    avatar?: string;
  };
  onLogout?: () => void;
  className?: string;
}

const TenantAwareNavbar: React.FC<NavbarProps> = ({
  user,
  onLogout,
  className = "",
}) => {
  const location = useLocation();
  const {
    currentOrganization,
    organizations,
    switchOrganization,
    isLoading,
    error
  } = useTenant();

  const navigation = [
    { name: 'Flows', href: '/flows', current: location.pathname.startsWith('/flows') },
    { name: 'Components', href: '/components', current: location.pathname.startsWith('/components') },
    { name: 'Variables', href: '/variables', current: location.pathname.startsWith('/variables') },
    { name: 'Projects', href: '/projects', current: location.pathname.startsWith('/projects') },
  ];

  const userNavigation = [
    { name: 'Your Profile', href: '/profile', icon: UserCircleIcon },
    { name: 'Organization Settings', href: '/tenant-management', icon: CogIcon },
    { name: 'Sign out', href: '#', icon: ArrowRightOnRectangleIcon, onClick: onLogout },
  ];

  const handleOrganizationChange = async (organization: any) => {
    try {
      await switchOrganization(organization.id);
      // Optionally redirect to refresh page data
      window.location.reload();
    } catch (error) {
      console.error('Failed to switch organization:', error);
    }
  };

  return (
    <Disclosure as="nav" className={`bg-white dark:bg-gray-800 shadow-sm border-b border-gray-200 dark:border-gray-700 ${className}`}>
      {({ open }) => (
        <>
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <div className="flex h-16 justify-between">
              {/* Left side */}
              <div className="flex">
                {/* Logo */}
                <div className="flex flex-shrink-0 items-center">
                  <Link to="/" className="flex items-center">
                    <img
                      className="h-8 w-auto"
                      src="/logo.svg"
                      alt="Langflow"
                    />
                    <span className="ml-2 text-xl font-semibold text-gray-900 dark:text-white">
                      Langflow
                    </span>
                  </Link>
                </div>

                {/* Navigation links */}
                <div className="hidden sm:ml-6 sm:flex sm:space-x-8">
                  {navigation.map((item) => (
                    <Link
                      key={item.name}
                      to={item.href}
                      className={`inline-flex items-center border-b-2 px-1 pt-1 text-sm font-medium ${
                        item.current
                          ? 'border-blue-500 text-gray-900 dark:text-white'
                          : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-300 dark:hover:text-white'
                      }`}
                    >
                      {item.name}
                    </Link>
                  ))}
                </div>
              </div>

              {/* Center - Search and Tenant Selector */}
              <div className="flex flex-1 items-center justify-center px-2 lg:ml-6 lg:justify-end">
                <div className="w-full max-w-lg lg:max-w-xs">
                  <div className="relative flex items-center space-x-4">
                    {/* Search */}
                    <div className="relative flex-1">
                      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                        <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
                      </div>
                      <input
                        className="block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 py-2 pl-10 pr-3 text-sm placeholder-gray-500 dark:placeholder-gray-400 focus:border-blue-500 focus:text-gray-900 dark:focus:text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
                        placeholder="Search flows, components..."
                        type="search"
                      />
                    </div>

                    {/* Tenant Selector */}
                    <div className="w-64">
                      {!isLoading && (
                        <TenantSelector
                          currentOrganization={currentOrganization}
                          organizations={organizations}
                          onOrganizationChange={handleOrganizationChange}
                          onCreateOrganization={() => {
                            // Navigate to organization creation
                            window.location.href = '/tenant-management';
                          }}
                        />
                      )}
                      {error && (
                        <div className="text-red-500 text-xs">
                          {error}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Right side */}
              <div className="hidden sm:ml-6 sm:flex sm:items-center">
                {/* Notifications */}
                <button
                  type="button"
                  className="rounded-full bg-white dark:bg-gray-800 p-1 text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                >
                  <span className="sr-only">View notifications</span>
                  <BellIcon className="h-6 w-6" aria-hidden="true" />
                </button>

                {/* User menu */}
                <Menu as="div" className="relative ml-3">
                  <div>
                    <Menu.Button className="flex max-w-xs items-center rounded-full bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">
                      <span className="sr-only">Open user menu</span>
                      {user?.avatar ? (
                        <img className="h-8 w-8 rounded-full" src={user.avatar} alt="" />
                      ) : (
                        <div className="h-8 w-8 rounded-full bg-gray-300 dark:bg-gray-600 flex items-center justify-center">
                          <span className="text-sm font-medium text-gray-700 dark:text-gray-200">
                            {user?.name?.charAt(0) || 'U'}
                          </span>
                        </div>
                      )}
                    </Menu.Button>
                  </div>
                  <Transition
                    as={React.Fragment}
                    enter="transition ease-out duration-200"
                    enterFrom="transform opacity-0 scale-95"
                    enterTo="transform opacity-100 scale-100"
                    leave="transition ease-in duration-75"
                    leaveFrom="transform opacity-100 scale-100"
                    leaveTo="transform opacity-0 scale-95"
                  >
                    <Menu.Items className="absolute right-0 z-50 mt-2 w-48 origin-top-right rounded-md bg-white dark:bg-gray-800 py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none">
                      {user && (
                        <div className="px-4 py-2 border-b border-gray-200 dark:border-gray-700">
                          <p className="text-sm font-medium text-gray-900 dark:text-white">{user.name}</p>
                          <p className="text-sm text-gray-500 dark:text-gray-400">{user.email}</p>
                        </div>
                      )}
                      {userNavigation.map((item) => (
                        <Menu.Item key={item.name}>
                          {({ active }) => (
                            item.onClick ? (
                              <button
                                onClick={item.onClick}
                                className={`w-full text-left px-4 py-2 text-sm ${
                                  active 
                                    ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white' 
                                    : 'text-gray-700 dark:text-gray-300'
                                }`}
                              >
                                <div className="flex items-center">
                                  <item.icon className="h-4 w-4 mr-2" />
                                  {item.name}
                                </div>
                              </button>
                            ) : (
                              <Link
                                to={item.href}
                                className={`block px-4 py-2 text-sm ${
                                  active 
                                    ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white' 
                                    : 'text-gray-700 dark:text-gray-300'
                                }`}
                              >
                                <div className="flex items-center">
                                  <item.icon className="h-4 w-4 mr-2" />
                                  {item.name}
                                </div>
                              </Link>
                            )
                          )}
                        </Menu.Item>
                      ))}
                    </Menu.Items>
                  </Transition>
                </Menu>
              </div>

              {/* Mobile menu button */}
              <div className="-mr-2 flex items-center sm:hidden">
                <Disclosure.Button className="inline-flex items-center justify-center rounded-md bg-white dark:bg-gray-800 p-2 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-inset">
                  <span className="sr-only">Open main menu</span>
                  {open ? (
                    <Bars3Icon className="block h-6 w-6" aria-hidden="true" />
                  ) : (
                    <Bars3Icon className="block h-6 w-6" aria-hidden="true" />
                  )}
                </Disclosure.Button>
              </div>
            </div>
          </div>

          {/* Mobile menu */}
          <Disclosure.Panel className="sm:hidden">
            <div className="space-y-1 pb-3 pt-2">
              {navigation.map((item) => (
                <Disclosure.Button
                  key={item.name}
                  as={Link}
                  to={item.href}
                  className={`block border-l-4 py-2 pl-3 pr-4 text-base font-medium ${
                    item.current
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/50 text-blue-700 dark:text-blue-100'
                      : 'border-transparent text-gray-600 dark:text-gray-300 hover:border-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 hover:text-gray-800 dark:hover:text-white'
                  }`}
                >
                  {item.name}
                </Disclosure.Button>
              ))}
            </div>

            {/* Mobile tenant selector */}
            <div className="border-t border-gray-200 dark:border-gray-700 pb-3 pt-4">
              <div className="px-4">
                {!isLoading && (
                  <TenantSelector
                    currentOrganization={currentOrganization}
                    organizations={organizations}
                    onOrganizationChange={handleOrganizationChange}
                    onCreateOrganization={() => {
                      window.location.href = '/tenant-management';
                    }}
                  />
                )}
              </div>
            </div>

            {/* Mobile user menu */}
            {user && (
              <div className="border-t border-gray-200 dark:border-gray-700 pb-3 pt-4">
                <div className="flex items-center px-4">
                  <div className="flex-shrink-0">
                    {user.avatar ? (
                      <img className="h-10 w-10 rounded-full" src={user.avatar} alt="" />
                    ) : (
                      <div className="h-10 w-10 rounded-full bg-gray-300 dark:bg-gray-600 flex items-center justify-center">
                        <span className="text-sm font-medium text-gray-700 dark:text-gray-200">
                          {user.name.charAt(0)}
                        </span>
                      </div>
                    )}
                  </div>
                  <div className="ml-3">
                    <div className="text-base font-medium text-gray-800 dark:text-white">{user.name}</div>
                    <div className="text-sm font-medium text-gray-500 dark:text-gray-400">{user.email}</div>
                  </div>
                </div>
                <div className="mt-3 space-y-1">
                  {userNavigation.map((item) => (
                    item.onClick ? (
                      <button
                        key={item.name}
                        onClick={item.onClick}
                        className="block w-full text-left px-4 py-2 text-base font-medium text-gray-500 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-800 dark:hover:text-white"
                      >
                        <div className="flex items-center">
                          <item.icon className="h-4 w-4 mr-2" />
                          {item.name}
                        </div>
                      </button>
                    ) : (
                      <Disclosure.Button
                        key={item.name}
                        as={Link}
                        to={item.href}
                        className="block px-4 py-2 text-base font-medium text-gray-500 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-800 dark:hover:text-white"
                      >
                        <div className="flex items-center">
                          <item.icon className="h-4 w-4 mr-2" />
                          {item.name}
                        </div>
                      </Disclosure.Button>
                    )
                  ))}
                </div>
              </div>
            )}
          </Disclosure.Panel>
        </>
      )}
    </Disclosure>
  );
};

export default TenantAwareNavbar;