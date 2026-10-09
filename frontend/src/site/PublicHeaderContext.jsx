import {createContext,useContext,useRef} from 'react';

const HeaderContext=createContext(null);
/** The bar reference stays stable across routes and phone-menu changes. */
export function PublicHeaderProvider({children}){
 const bar=useRef(null);
 return <HeaderContext.Provider value={bar}>{children}</HeaderContext.Provider>;
}
export function usePublicHeader(){return useContext(HeaderContext);}
