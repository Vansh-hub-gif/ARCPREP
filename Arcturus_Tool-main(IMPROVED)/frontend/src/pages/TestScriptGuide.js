import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeftIcon, DocumentArrowUpIcon } from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import axios from 'axios';
import API_BASE from '../config';

function TestScriptGuide() {
  const navigate = useNavigate();
  const [jobId, setJobId] = useState('');
  const [mappingFile, setMappingFile] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleGenerate = async () => {
    if (!jobId) {
      toast.error('Please enter a Job ID');
      return;
    }

    if (!mappingFile) {
      toast.error('Please upload the HR test-script mapping Excel file');
      return;
    }

    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('mapping_file', mappingFile);

      const response = await axios.post(
        `${API_BASE}/generate-test-scripts/${jobId}`,
        formData,
        {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('token')}`
          },
          responseType: 'blob'
        }
      );

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'OQUAT_UAT_Test_Scripts.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      toast.success('Test scripts generated!');
    } catch (error) {
      // Blob responses need to be decoded before displaying FastAPI's detail.
      let message = 'Generation failed';

      if (error.response?.data instanceof Blob) {
        try {
          const text = await error.response.data.text();
          const parsed = JSON.parse(text);
          message = parsed.detail || message;
        } catch (_) {
          // Keep the generic message when the response is not JSON.
        }
      } else {
        message = error.response?.data?.detail || message;
      }

      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center">
          <button onClick={() => navigate('/dashboard')} className="mr-4 text-gray-600 hover:text-gray-800">
            <ArrowLeftIcon className="w-5 h-5" />
          </button>
          <h1 className="text-xl font-semibold text-gray-800">Test Script Generation Guide</h1>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="bg-white rounded-xl shadow-md p-8">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">Generate UAT Test Scripts</h2>
          <p className="text-gray-500 text-sm mb-6">
            Enter the Job ID from a completed feature extraction and upload the HR script-mapping workbook.
            The uploaded Script Number is mapped to each feature using the extension reference matching.
          </p>

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-1">Job ID</label>
            <input
              type="text"
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              placeholder="e.g., 123e4567-e89b-12d3-a456-426614174000"
              className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent"
            />
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              HR Test Script Mapping Excel
            </label>

            <label className="flex items-center justify-center w-full min-h-28 border-2 border-dashed border-gray-300 rounded-lg cursor-pointer hover:border-green-500 hover:bg-green-50 transition">
              <div className="text-center px-4 py-4">
                <DocumentArrowUpIcon className="w-8 h-8 mx-auto text-gray-400 mb-2" />
                {mappingFile ? (
                  <>
                    <p className="text-sm font-medium text-gray-700">{mappingFile.name}</p>
                    <p className="text-xs text-green-600 mt-1">Mapping workbook selected</p>
                  </>
                ) : (
                  <>
                    <p className="text-sm font-medium text-gray-700">Upload mapping workbook</p>
                    <p className="text-xs text-gray-500 mt-1">.xlsx file containing Script Number and Script Name/ Scenarios</p>
                  </>
                )}
              </div>
              <input
                type="file"
                accept=".xlsx,.xls"
                className="hidden"
                onChange={(e) => setMappingFile(e.target.files?.[0] || null)}
              />
            </label>
          </div>

          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
            <p className="text-sm text-blue-700">
              The mapping workbook controls the available Test Case IDs. Excel and PowerPoint extraction output is not changed by this step.
            </p>
          </div>

          <button
            onClick={handleGenerate}
            disabled={loading}
            className="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-3 rounded-lg transition duration-200 disabled:opacity-50"
          >
            {loading ? 'Generating...' : 'Generate Test Scripts'}
          </button>
        </div>
      </main>
    </div>
  );
}

export default TestScriptGuide;
