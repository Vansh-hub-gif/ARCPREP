import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import ExtractGuide from './pages/ExtractGuide';
import TestScriptGuide from './pages/TestScriptGuide';
import ProtectedRoute from './components/ProtectedRoute';
import ProgressTracker from './components/ProgressTracker';

function App() {
  return (
    <Router>
      <Toaster position="top-right" />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/" element={<Navigate to="/dashboard" />} />
        <Route path="/dashboard" element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        } />
        <Route path="/extract-guide" element={
          <ProtectedRoute>
            <ExtractGuide />
          </ProtectedRoute>
        } />
        <Route path="/test-script-guide" element={
          <ProtectedRoute>
            <TestScriptGuide />
          </ProtectedRoute>
        } />
        {/* Add ProgressTracker as a new route */}
        <Route path="/progress" element={
          <ProtectedRoute>
            <div className="App">
              <ProgressTracker />
            </div>
          </ProtectedRoute>
        } />
      </Routes>
    </Router>
  );
}

export default App;