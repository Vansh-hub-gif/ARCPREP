// Central backend base URL.
// Defaults to the deployed engine so existing behaviour is unchanged.
// Override for local development by creating frontend/.env.local with:
//   REACT_APP_API_URL=http://localhost:8000
const API_BASE =
  process.env.REACT_APP_API_URL || 'https://oquat-intelligence-engine.onrender.com';

export default API_BASE;
