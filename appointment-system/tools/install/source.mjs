/** Run the contained source exporter. This command never uploads or deploys. */
import {spawnSync} from 'node:child_process';
import {basename,delimiter,dirname,join,resolve} from 'node:path';
const packageRoot=resolve(import.meta.dirname,'../..');
if(basename(packageRoot)!=='appointment-system')throw new Error('Run this command from an installed project copy.');
const root=dirname(packageRoot);
const python=process.env.BOOKING_SETUP_PYTHON||(process.platform==='win32'?'python':'python3');
const result=spawnSync(python,['-m','tools.install.source',root,'--expected-root',root],{
 cwd:root,shell:false,stdio:'inherit',timeout:120_000,
 env:{...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONPATH:[packageRoot,join(packageRoot,'engine')].join(delimiter)},
});
if(result.error){console.error('Hosting preparation could not start. Select a Python environment with the contained dependencies.');process.exit(1);}
process.exit(result.status??1);
