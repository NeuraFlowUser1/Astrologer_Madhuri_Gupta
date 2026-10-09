import {Detail} from './ServiceDetail.jsx';
import copy from '../site/public-copy.json';
export default function KundliPrediction(){return <Detail service={copy.services.find(s=>s.id==='kundli-prediction')}/>;}
