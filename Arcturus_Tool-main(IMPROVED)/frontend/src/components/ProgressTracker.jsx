import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  DocumentArrowDownIcon, 
  DocumentTextIcon,
  ArrowRightOnRectangleIcon,
  UserCircleIcon,
  XMarkIcon
} from '@heroicons/react/24/outline';
import ProgressTracker from '../components/ProgressTracker';
import '../components/ProgressTracker.css';

function Dashboard() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [showExtractor, setShowExtractor] = useState(false);

  useEffect(() => {
    const userData = localStorage.getItem('user');
    if (userData) {
      setUser(JSON.parse(userData));
    }
  }, []);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex justify-between items-center">
          <div className="flex items-center space-x-2">
            <span className="text-2xl font-bold text-blue-700">⚡ OQUAT</span>
            <span className="text-sm text-gray-500">Intelligence Platform</span>
          </div>
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2 text-sm text-gray-700">
              <UserCircleIcon className="w-5 h-5" />
              <span>{user?.full_name || user?.email}</span>
            </div>
            <button
              onClick={handleLogout}
              className="flex items-center space-x-1 text-sm text-red-600 hover:text-red-700"
            >
              <ArrowRightOnRectangleIcon className="w-4 h-4" />
              <span>Logout</span>
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="text-center mb-12">
          <h1 className="text-3xl font-bold text-gray-800">Welcome to OQUAT Platform</h1>
          <p className="text-gray-500 mt-2">Select a module to get started</p>
        </div>

        <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
          {/* Excel & PPT Generation Card */}
          <div 
            onClick={() => setShowExtractor(true)}
            className="bg-white rounded-2xl shadow-lg hover:shadow-xl transition-shadow duration-300 p-8 cursor-pointer border border-gray-100 hover:border-blue-300"
          >
            <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-4">
              <DocumentArrowDownIcon className="w-8 h-8 text-blue-600" />
            </div>
            <h2 className="text-xl font-semibold text-gray-800">Excel & PPT Generation</h2>
            <p className="text-gray-500 text-sm mt-2">
              Extract Oracle features and generate comprehensive Excel reports and PowerPoint presentations.
            </p>
            <div className="mt-4 flex items-center text-blue-600 text-sm font-medium">
              Start Guide →
            </div>
          </div>

          {/* Test Script Generation Card */}
          <div 
            onClick={() => navigate('/test-script-guide')}
            className="bg-white rounded-2xl shadow-lg hover:shadow-xl transition-shadow duration-300 p-8 cursor-pointer border border-gray-100 hover:border-green-300"
          >
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mb-4">
              <DocumentTextIcon className="w-8 h-8 text-green-600" />
            </div>
            <h2 className="text-xl font-semibold text-gray-800">Test Script Generation</h2>
            <p className="text-gray-500 text-sm mt-2">
              Map Oracle features to test scripts and generate UAT test script Excel files.
            </p>
            <div className="mt-4 flex items-center text-green-600 text-sm font-medium">
              Start Guide →
            </div>
          </div>
        </div>
      </main>

      {/* ProgressTracker Modal - Fixed with proper overlay */}
      {showExtractor && (
        <div className="extractor-modal-overlay" onClick={() => setShowExtractor(false)}>
          <div className="extractor-modal-content" onClick={(e) => e.stopPropagation()}>
            <button 
              onClick={() => setShowExtractor(false)}
              className="extractor-modal-close"
            >
              <XMarkIcon className="w-6 h-6" />
            </button>
            <ProgressTracker />
          </div>
        </div>
      )}
    </div>
  );
}

export default Dashboard;