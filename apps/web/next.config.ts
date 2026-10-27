import type { NextConfig } from 'next';
const config: NextConfig = {output:'export',basePath:'/pubster',trailingSlash:true,images:{unoptimized:true},productionBrowserSourceMaps:false,experimental:{cpus:1}};
export default config;
