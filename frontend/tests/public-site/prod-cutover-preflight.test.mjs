// @vitest-environment node
import {afterAll,beforeAll,expect,test} from 'vitest';
import {mkdtempSync,mkdirSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {resolve,dirname} from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {runChecks,checkApprovedClientSettings,checkProtectedPaths,checkAssets} from '../../scripts/check-public-site.mjs';

const project=fileURLToPath(new URL('../../../',import.meta.url));
const original='7f6fc4eddc4b67a3265329a13696d2be488613b7';
const settings=['business-settings','project','booking-browser','enquiry-browser','staff-browser','public-assets','hosting-files','monitor','backup'].map(n=>'appointment-settings/'+n+'.json');
const names=['appointment-background-monitor.yml','appointment-database-backup.yml','appointment-backup-validation.yml'];
const owned=[...settings,'workers/booking-recovery/wrangler.json',...names.map(n=>'.github/workflows/'+n)];
let temporary,baseline;
const put=(path,body)=>{const target=resolve(temporary,path);mkdirSync(dirname(target),{recursive:true});writeFileSync(target,body);};
const reset=()=>{
 for(const path of owned)put(path,readFileSync(resolve(project,path)));
 for(const name of ['monitor','backup']){const path='appointment-settings/'+name+'.json',value=JSON.parse(readFileSync(resolve(temporary,path)));value.version=1;delete value.production_branch;put(path,JSON.stringify(value));}
 for(const name of names)put('.github/workflows/'+name,readFileSync(resolve(project,'appointment-system/deploy/workflows',name)));
};
beforeAll(()=>{
 temporary=mkdtempSync(resolve(tmpdir(),'sarsa-prod-preflight-'));
 execFileSync('git',['init','-q',temporary]);
 for(const path of owned)put(path,execFileSync('git',['show',original+':'+path],{cwd:project}));
 execFileSync('git',['add','.'],{cwd:temporary});
 execFileSync('git',['-c','user.name=Disconnected test','-c','user.email=synthetic@example.test','commit','-qm','Synthetic preflight baseline'],{cwd:temporary});
 baseline=execFileSync('git',['rev-parse','HEAD'],{cwd:temporary,encoding:'utf8'}).trim();
 mkdirSync(resolve(temporary,'frontend/src'),{recursive:true});
 for(const name of names)put('appointment-system/deploy/workflows/'+name,readFileSync(resolve(project,'appointment-system/deploy/workflows',name)));
 reset();
});
afterAll(()=>rmSync(temporary,{recursive:true,force:true}));

test('actual receiving preflight accepts only the verified new package and preserved public site',()=>{
 const result=runChecks();expect(result.routes).toHaveLength(16);expect(result.source).toContain('src/booking/booking-ui.jsx');
},60000);

test('main and prod configurations must agree with every exact owned workflow and setting',()=>{
 reset();expect(checkApprovedClientSettings(temporary,baseline)).toHaveLength(8);
 for(const name of ['monitor','backup']){
  const path='appointment-settings/'+name+'.json',value=JSON.parse(readFileSync(resolve(temporary,path)));
  put(path,JSON.stringify({...value,version:2,production_branch:'prod'}));
 }
 const script="import json,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from tools.automation.production import render_workflow;root=Path(sys.argv[1]);names=json.loads(sys.argv[2]);print(json.dumps({n:render_workflow(n,(root/'deploy/workflows'/n).read_bytes(),'prod').decode() for n in names}))";
 const workflows=JSON.parse(execFileSync('python3',['-c',script,resolve(project,'appointment-system'),JSON.stringify(names)],{encoding:'utf8'}));
 for(const [name,text] of Object.entries(workflows))put('.github/workflows/'+name,text);
 expect(checkApprovedClientSettings(temporary,baseline)).toHaveLength(8);
 for(const change of [{version:true},{version:2,production_branch:'main'},{extra:true}]){
  const path='appointment-settings/monitor.json',before=readFileSync(resolve(temporary,path));
  put(path,JSON.stringify({...JSON.parse(before),...change}));expect(()=>checkApprovedClientSettings(temporary,baseline)).toThrow('automation configuration');put(path,before);
 }
 for(const name of names){const path='.github/workflows/'+name,before=readFileSync(resolve(temporary,path));put(path,before+'\n# unreviewed change');expect(()=>checkApprovedClientSettings(temporary,baseline)).toThrow('automation workflow');put(path,before);}
 const backup='appointment-settings/backup.json',before=readFileSync(resolve(temporary,backup));put(backup,JSON.stringify({...JSON.parse(before),owner_email:'foreign@example.test'}));expect(()=>checkApprovedClientSettings(temporary,baseline)).toThrow('automation configuration');put(backup,before);
 reset();
},60000);

test('unapproved business, browser, worker and source-export changes remain forbidden',()=>{
 for(const path of settings.slice(0,7).concat('workers/booking-recovery/wrangler.json')){
  reset();const before=JSON.parse(readFileSync(resolve(temporary,path)));put(path,JSON.stringify({...before,unreviewed:true}));expect(()=>checkApprovedClientSettings(temporary,baseline)).toThrow();
 }
 reset();put('frontend/src/unexported.mjs','export const synthetic=true;');expect(()=>checkApprovedClientSettings(temporary,baseline)).toThrow('absent from the official hosting export');rmSync(resolve(temporary,'frontend/src/unexported.mjs'));
},60000);

test('every protected boundary refuses and public asset classification stays complete',()=>{
 for(const path of ['appointment-system/engine/x.py','workers/x.mjs','api/index.py','backend/x.py','.github/workflows/x.yml','appointment-settings/project.json','requirements.txt','pyproject.toml','vercel.json','package.json','package-lock.json','frontend/package-lock.json'])expect(()=>checkProtectedPaths([path])).toThrow('Protected backend');
 expect(()=>checkProtectedPaths(['frontend/src/App.jsx','appointment-settings/public-assets.json'])).not.toThrow();
 const assets=JSON.parse(readFileSync(resolve(project,'appointment-settings/public-assets.json')));delete assets['/media/consultation-still-life.png'];expect(()=>checkAssets(assets,resolve(project,'frontend/public'))).toThrow('Unclassified public asset');
});
