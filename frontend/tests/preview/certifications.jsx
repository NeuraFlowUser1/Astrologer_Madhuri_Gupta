/** Private inspectable design preview. Never a production entry or public route. */
import React,{StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import Certifications from '../../src/site/Certifications.jsx';
createRoot(document.getElementById('root')).render(<StrictMode><Certifications/></StrictMode>);
