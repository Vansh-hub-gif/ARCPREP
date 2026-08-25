import React,{ useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  ArrowLeftIcon, 
  DocumentArrowDownIcon,
  PresentationChartBarIcon,
  CloudArrowUpIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  ArrowPathIcon,
  DocumentTextIcon
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import axios from 'axios';
import API_BASE from '../config';

function ExtractGuide() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [features, setFeatures] = useState([]);
  const [processedCount, setProcessedCount] = useState(0);
  const [totalFeatures, setTotalFeatures] = useState(0);
  const [currentFeature, setCurrentFeature] = useState('');
  const [isPolling, setIsPolling] = useState(false);
  const [excelUrl, setExcelUrl] = useState(null);
  const [pptUrl, setPptUrl] = useState(null);
  const [elapsedTime, setElapsedTime] = useState(0);

  // Timer for elapsed time
  useEffect(() => {
    let interval;
    if (isPolling) {
      interval = setInterval(() => {
        setElapsedTime(prev => prev + 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [isPolling]);

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const handleExtract = async () => {
  if (!url) {
    toast.error('Please enter an Oracle documentation URL');
    return;
  }

  setLoading(true);
  setElapsedTime(0);
  setProcessedCount(0);
  setFeatures([]);
  setCurrentFeature('');
  
  try {
    const token = localStorage.getItem('token');
    
    toast.loading('Scraping Oracle page...', { id: 'scrape' });
    
    const scrapeResponse = await axios.post(`${API_BASE}/scrape`, {
      url: url
    }, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    });

    const extractedFeatures = scrapeResponse.data.features;
    
    if (extractedFeatures.length === 0) {
      toast.error('No features found on this Oracle page.', { id: 'scrape' });
      setLoading(false);
      return;
    }

    toast.success(`Found ${extractedFeatures.length} features!`, { id: 'scrape' });

    // Extract feature names from objects
    const featureNames = extractedFeatures.map(feature => {
      // If it's an object, try to get the title or name
      if (typeof feature === 'object') {
        return feature.title || feature.name || feature.module || JSON.stringify(feature);
      }
      return feature;
    });

    toast.loading('Starting extraction pipeline...', { id: 'extract' });

    const response = await axios.post(`${API_BASE}/extract`, {
      url: url,
      limit: 1000,
      features: extractedFeatures,
      script_mappings: []
    }, {
      headers: {
        Authorization: `Bearer ${token}`
      }
    });

    setJobId(response.data.job_id);
    setTotalFeatures(extractedFeatures.length);
    setFeatures(featureNames); // Store the feature names (strings)
    setStep(2);
    setIsPolling(true);
    
    toast.success('Extraction started!', { id: 'extract' });
    
    pollStatus(response.data.job_id);
  } catch (error) {
    console.error('Extraction error:', error);
    // The backend returns `detail` as an OBJECT for feature-URL validation
    // failures. Passing an object straight to toast.error() renders
    // "[object Object]" (or throws in React), which hid the real cause of
    // every 400. Normalize to a string first.
    const detail = error.response?.data?.detail;
    let message = 'Extraction failed';
    if (typeof detail === 'string') {
      message = detail;
    } else if (detail && typeof detail === 'object') {
      message = detail.message
        ? `${detail.message} ${JSON.stringify(detail.examples || '')}`
        : JSON.stringify(detail);
    }
    toast.error(message);
    setLoading(false);
  }
};

const pollStatus = (jobId) => {
  const token = localStorage.getItem('token');
  const interval = setInterval(async () => {
    try {
      const response = await axios.get(`${API_BASE}/status/${jobId}`, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      });
      
      const data = response.data;
      console.log('Status update:', data);
      setJobStatus(data);
      
      if (data.status === 'Enriching') {
        const processed = data.processed || 0;
        setProcessedCount(processed);
        
        let featureName = data.current_feature || '';
        if (typeof featureName === 'object') {
          featureName = featureName.title || featureName.name || featureName.module || 'Processing...';
        }
        setCurrentFeature(featureName);
        
        console.log(`[ENRICH] ${processed + 1}/${totalFeatures}: ${featureName}`);
      }
      
      if (data.status === 'Generating Files') {
        setProcessedCount(data.feature_count || totalFeatures);
        setJobStatus({ ...data, status: 'Generating Files' });
        toast.loading('Generating reports...', { id: 'extract' });
      }
      
      if (data.status === 'Completed') {
        clearInterval(interval);
        setIsPolling(false);
        setProcessedCount(data.feature_count || totalFeatures);
        setCurrentFeature('');
        
        if (data.excel_url) {
          setExcelUrl(data.excel_url);
        }
        if (data.ppt_url) {
          setPptUrl(data.ppt_url);
        }
        
        setStep(3);  // ← FIXED: Changed from 4 to 3
        toast.success('✅ Reports ready!', { id: 'extract' });
        setLoading(false);
      }
      
      if (data.status === 'Failed') {
        clearInterval(interval);
        setIsPolling(false);
        toast.error('Extraction failed');
        setStep(3);  // ← FIXED: Changed from 4 to 3
        setLoading(false);
      }
    } catch (error) {
      console.error('Polling error:', error);
    }
  }, 2000);
};

  const handleDownload = (url, filename) => {
    window.open(`${API_BASE}${url}`, '_blank');
    toast.success(`Downloading ${filename}...`);
  };

  // Progress percentage
  const progressPercentage = totalFeatures > 0 ? Math.round((processedCount / totalFeatures) * 100) : 0;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-sm shadow-sm border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <button 
              onClick={() => navigate('/dashboard')} 
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors duration-200"
            >
              <ArrowLeftIcon className="w-5 h-5 text-gray-600" />
            </button>
            <div>
              <h1 className="text-xl font-semibold text-gray-800">📊 Excel & PPT Generation</h1>
              <p className="text-sm text-gray-500">Extract Oracle features and generate professional reports</p>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <span className="text-xs bg-blue-100 text-blue-700 px-3 py-1 rounded-full font-medium">
              v2.0
            </span>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Steps indicator */}
        {/* Steps indicator */}
<div className="mb-8">
  <div className="flex items-center justify-between max-w-2xl mx-auto">
    {[
      { num: 1, label: 'Enter URL' },
      { num: 2, label: 'Processing' },
      { num: 3, label: 'Download' }  // ← Changed from 3 to 3 (already correct)
    ].map((s) => (
      <div key={s.num} className="flex items-center">
        <div className={`flex items-center justify-center w-10 h-10 rounded-full text-sm font-semibold transition-all duration-300 ${
          s.num < step ? 'bg-green-500 text-white' :
          s.num === step ? 'bg-blue-600 text-white shadow-lg shadow-blue-200 scale-105' :
          'bg-gray-200 text-gray-500'
        }`}>
          {s.num < step ? <CheckCircleIcon className="w-5 h-5" /> : s.num}
        </div>
        {s.num < 3 && (
          <div className={`w-16 h-1 mx-2 rounded-full transition-all duration-300 ${
            s.num < step ? 'bg-green-500' :
            s.num === step ? 'bg-blue-400' :
            'bg-gray-200'
          }`} />
        )}
      </div>
    ))}
  </div>
  <div className="flex justify-between max-w-2xl mx-auto mt-2 px-2">
    {['Enter URL', 'Processing', 'Download'].map((label, i) => (
      <span key={i} className={`text-xs font-medium ${
        i + 1 <= step ? 'text-blue-600' : 'text-gray-400'
      }`}>
        {label}
      </span>
    ))}
  </div>
</div>

        {/* Step 1: Enter URL */}
        {step === 1 && (
          <div className="bg-white rounded-2xl shadow-xl border border-gray-100 p-8">
            <div className="flex items-start space-x-4 mb-6">
              <div className="p-3 bg-blue-50 rounded-xl">
                <CloudArrowUpIcon className="w-6 h-6 text-blue-600" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-800">Enter Oracle Documentation URL</h2>
                <p className="text-gray-500 text-sm mt-1">
                  Paste the URL of the Oracle What's New page you want to extract features from.
                </p>
              </div>
            </div>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Oracle Page URL</label>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value.trim())}
                  placeholder="https://docs.oracle.com/..."
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200"
                  onKeyDown={(e) => e.key === 'Enter' && handleExtract()}
                />
              </div>
              <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
                <p className="text-sm text-blue-700 flex items-start">
                  <span className="mr-2">💡</span>
                  Example: <span className="font-mono text-xs ml-1">https://docs.oracle.com/en/cloud/saas/readiness/scm/26b/inv26b/26B-inventory-wn-t73741.htm</span>
                </p>
              </div>
              <button
                onClick={handleExtract}
                disabled={!url || loading}
                className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 px-6 rounded-xl transition-all duration-200 flex items-center justify-center space-x-2"
              >
                {loading ? (
                  <>
                    <ArrowPathIcon className="w-5 h-5 animate-spin" />
                    <span>Processing...</span>
                  </>
                ) : (
                  <>
                    <span>Start Extraction</span>
                    <span>→</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Processing */}
{step === 2 && (
  <div className="bg-white rounded-2xl shadow-xl border border-gray-100 p-8">
    <div className="text-center mb-8">
      <div className="relative inline-block">
        <div className="w-20 h-20 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto"></div>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-sm font-bold text-blue-600">{progressPercentage}%</span>
        </div>
      </div>
      <h2 className="text-xl font-semibold text-gray-800 mt-4">Processing Features</h2>
      <p className="text-gray-500 text-sm mt-1">
        Please wait while we extract and enrich your features...
      </p>
    </div>

    {/* Stats Grid */}
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div className="bg-blue-50 rounded-xl p-4 text-center">
        <div className="text-2xl font-bold text-blue-600">{totalFeatures}</div>
        <div className="text-xs text-blue-600 font-medium mt-1">Total Features</div>
      </div>
      <div className="bg-green-50 rounded-xl p-4 text-center">
        <div className="text-2xl font-bold text-green-600">{processedCount}</div>
        <div className="text-xs text-green-600 font-medium mt-1">Processed</div>
      </div>
      <div className="bg-purple-50 rounded-xl p-4 text-center">
        <div className="text-2xl font-bold text-purple-600">{progressPercentage}%</div>
        <div className="text-xs text-purple-600 font-medium mt-1">Complete</div>
      </div>
      <div className="bg-orange-50 rounded-xl p-4 text-center">
        <div className="text-2xl font-bold text-orange-600">{formatTime(elapsedTime)}</div>
        <div className="text-xs text-orange-600 font-medium mt-1">Elapsed Time</div>
      </div>
    </div>

    {/* Progress Bar */}
    <div className="w-full bg-gray-200 rounded-full h-3 mb-4 overflow-hidden">
      <div 
        className="h-full bg-gradient-to-r from-blue-500 to-blue-600 rounded-full transition-all duration-500 ease-out"
        style={{ width: `${progressPercentage}%` }}
      />
    </div>

    {/* ===== FEATURE PROCESSING LOGS ===== */}
<div className="bg-gray-50 rounded-xl p-4 border border-gray-200 max-h-60 overflow-y-auto">
  <div className="flex items-center justify-between mb-3">
    <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Processing Log</span>
    <span className="text-xs text-gray-400">{processedCount}/{totalFeatures} features</span>
  </div>
  
  {/* Show processed features with checkmarks */}
  {features.slice(0, processedCount).map((feature, index) => {
    // Handle if feature is an object
    let featureDisplay = feature;
    if (typeof feature === 'object') {
      featureDisplay = feature.title || feature.name || feature.module || JSON.stringify(feature);
    }
    return (
      <div key={index} className="flex items-center space-x-2 py-1.5 border-b border-gray-100 last:border-0">
        <CheckCircleIcon className="w-4 h-4 text-green-500 flex-shrink-0" />
        <span className="text-sm text-gray-600 truncate">
          [{index + 1}/{totalFeatures}] {featureDisplay}
        </span>
        <span className="text-xs text-green-500 ml-auto flex-shrink-0">✓ Done</span>
      </div>
    );
  })}
  
  {/* Show currently processing feature with spinning icon */}
  {currentFeature && processedCount < totalFeatures && (
    <div className="flex items-center space-x-2 py-1.5 border-b border-gray-100 bg-blue-50 rounded-lg px-2 -mx-2">
      <ArrowPathIcon className="w-4 h-4 text-blue-500 animate-spin flex-shrink-0" />
      <span className="text-sm text-blue-600 font-medium truncate">
        [{processedCount + 1}/{totalFeatures}] {currentFeature}
      </span>
      <span className="text-xs text-blue-500 ml-auto flex-shrink-0">⏳ Processing...</span>
    </div>
  )}
  
  {/* Show pending features count */}
  {processedCount < totalFeatures && !currentFeature && (
    <div className="flex items-center space-x-2 py-1.5">
      <ClockIcon className="w-4 h-4 text-gray-400 flex-shrink-0" />
      <span className="text-sm text-gray-400">
        Waiting for next feature...
      </span>
    </div>
  )}
  
  {/* All done message */}
  {processedCount === totalFeatures && totalFeatures > 0 && (
    <div className="flex items-center space-x-2 py-1.5">
      <CheckCircleIcon className="w-4 h-4 text-green-500 flex-shrink-0" />
      <span className="text-sm text-green-600 font-medium">
        ✅ All {totalFeatures} features processed successfully!
      </span>
    </div>
  )}
</div>
{/* ===== END FEATURE PROCESSING LOGS ===== */}
    {/* ===== END FEATURE PROCESSING LOGS ===== */}

    {jobId && (
      <div className="mt-4 text-center">
        <p className="text-xs text-gray-400 inline-flex items-center gap-2">
          Job ID: <span className="font-mono">{jobId}</span>
          <button
            type="button"
            onClick={() => {
              navigator.clipboard.writeText(jobId);
              toast.success('Job ID copied');
            }}
            className="text-blue-500 hover:text-blue-700 underline"
          >
            Copy
          </button>
        </p>
      </div>
    )}
  </div>
)}
        {/* Step 3: Download */}
        {step === 3 && (
          <div className="bg-white rounded-2xl shadow-xl border border-gray-100 p-8">
            <div className="text-center mb-8">
              <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <CheckCircleIcon className="w-10 h-10 text-green-600" />
              </div>
              <h2 className="text-2xl font-bold text-gray-800">Reports Ready! 🎉</h2>
              <p className="text-gray-500 mt-2">
                Your Excel and PowerPoint reports have been generated successfully.
              </p>
              <div className="mt-2 text-sm text-green-600 bg-green-50 px-4 py-2 rounded-full inline-block">
                ✅ {totalFeatures} features processed
              </div>
            </div>

            {/* Stats Summary */}
            <div className="grid grid-cols-3 gap-4 mb-8">
              <div className="bg-blue-50 rounded-xl p-4 text-center">
                <div className="text-2xl font-bold text-blue-600">{totalFeatures}</div>
                <div className="text-xs text-blue-600 font-medium mt-1">Features</div>
              </div>
              <div className="bg-green-50 rounded-xl p-4 text-center">
                <div className="text-2xl font-bold text-green-600">{formatTime(elapsedTime)}</div>
                <div className="text-xs text-green-600 font-medium mt-1">Processing Time</div>
              </div>
              <div className="bg-purple-50 rounded-xl p-4 text-center">
                <div className="text-2xl font-bold text-purple-600">2</div>
                <div className="text-xs text-purple-600 font-medium mt-1">Files Ready</div>
              </div>
            </div>

            {/* Download Buttons */}
            <div className="grid md:grid-cols-2 gap-4">
              <button
                onClick={() => handleDownload(excelUrl || `/outputs/oracle_report.xlsx`, 'Excel Report')}
                className="group relative overflow-hidden bg-gradient-to-br from-green-500 to-green-600 hover:from-green-600 hover:to-green-700 text-white font-semibold py-6 px-6 rounded-2xl transition-all duration-300 shadow-lg hover:shadow-xl"
              >
                <div className="absolute inset-0 bg-white/10 group-hover:bg-white/20 transition-all duration-300" />
                <div className="relative flex items-center justify-center space-x-3">
                  <DocumentArrowDownIcon className="w-8 h-8" />
                  <div className="text-left">
                    <div className="text-sm font-medium">Download Excel Report</div>
                    <div className="text-xs opacity-80">.xlsx file</div>
                  </div>
                </div>
              </button>

              <button
                onClick={() => handleDownload(pptUrl || `/outputs/oracle_report.pptx`, 'PowerPoint')}
                className="group relative overflow-hidden bg-gradient-to-br from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 text-white font-semibold py-6 px-6 rounded-2xl transition-all duration-300 shadow-lg hover:shadow-xl"
              >
                <div className="absolute inset-0 bg-white/10 group-hover:bg-white/20 transition-all duration-300" />
                <div className="relative flex items-center justify-center space-x-3">
                  <PresentationChartBarIcon className="w-8 h-8" />
                  <div className="text-left">
                    <div className="text-sm font-medium">Download PowerPoint</div>
                    <div className="text-xs opacity-80">.pptx file</div>
                  </div>
                </div>
              </button>
            </div>

            {/* Divider with "OR" */}
            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200"></div>
              </div>
              <div className="relative flex justify-center">
                <span className="bg-white px-4 text-sm text-gray-400">or</span>
              </div>
            </div>

            {/* Back to Dashboard */}
            <button
              onClick={() => navigate('/dashboard')}
              className="w-full bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-3 px-6 rounded-xl transition-all duration-200 flex items-center justify-center space-x-2"
            >
              <ArrowLeftIcon className="w-5 h-5" />
              <span>Back to Dashboard</span>
            </button>
          </div>
        )}
      </main>
    </div>
  );
}

export default ExtractGuide;